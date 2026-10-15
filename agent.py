"""Planner-Executor agent loop: intent -> recipe -> MCP tool chain -> report.

Proactive memory & learning (Phase 1/2):
  - planning injects past experience (recency/env-aware), the last
    successful run for the recipe (success-path replay), per-step success
    stats and a risk list (skills with proven high failure rates);
  - a failed run reflects immediately: similar past failures and their
    retry strategies are attached to the report so the next attempt starts
    from what was learned, and recurring domain failures trigger an
    automatic knowledge distillation (memory-keeper).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field

from .mcp_adapter import McpAdapter
from .local_tools import LOCAL_TOOLS, call_local
from .experience import ExperienceStore
from .failure_taxonomy import classify_failure, retry_strategy_for
from .planner import KeywordPlanner
from .recipes import RECIPES
from .report_store import ReportStore
from .skill_registry import SkillRegistry
from .domain_flows import DOMAIN_FLOWS

_log = logging.getLogger("chip_ai_agent.learning")

# recurring domain failures above this threshold trigger an automatic
# knowledge distillation at the end of a failed run (opt-out:
# CHIP_AGENT_AUTO_DISTILL=0)
AUTO_DISTILL_MIN_RECORDS = 5


@dataclass
class StepResult:
    skill: str
    why: str
    ok: bool
    detail: str
    target: str | None = None
    failure_class: str | None = None
    retry_strategy: str | None = None
    duration: float | None = None


@dataclass
class RunReport:
    intent: str
    recipe: str
    title: str
    run_id: int | None = None
    steps: list[StepResult] = field(default_factory=list)
    # trial trajectory: consecutive attempts of the same intent+recipe
    attempt: int = 1
    # learning output: similar past failures (with retry strategies) and
    # the proactive actions taken during this run
    reflections: list[dict] = field(default_factory=list)
    learned: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"# Agent Run — {self.title}", f"Intent: {self.intent}",
                 f"Attempt: {self.attempt}", ""]
        for i, s in enumerate(self.steps, 1):
            mark = "OK " if s.ok else "ERR"
            lines.append(f"{i}. [{mark}] {s.skill} — {s.why}")
            if s.detail:
                lines.append(f"   -> {s.detail}")
        if self.reflections or self.learned:
            lines += ["", "## Learning (主动记忆)"]
            for r in self.reflections:
                if "previous_attempt" in r:    # trial-trajectory comparison
                    pa = r["previous_attempt"]
                    failed = ", ".join(pa.get("failed_skills") or ["(无)"])
                    lines.append(f"- 上次尝试 (run #{pa.get('run_id')}): "
                                 f"失败技能 [{failed}]"
                                 + (f"; recipe 漂移: 上次 {pa.get('recipe')!r}"
                                    if pa.get("recipe_drift") else ""))
                elif "skill" in r:          # per-skill historical failure entry
                    tops = ", ".join(f"{fc}×{n}"
                                     for fc, n in r.get("historical_failures", []))
                    strats = " / ".join(dict.fromkeys(
                        r.get("strategies") or [])) or "未知"
                    lines.append(f"- 技能 {r['skill']} 历史失败: {tops}"
                                 f" (历史策略: {strats}) — {r.get('note', '')}")
                else:                     # similar past failure entry
                    lines.append(
                        f"- 相似历史失败 [{r.get('failure_class')}] (score="
                        f"{r.get('score')}): retry={r.get('retry_strategy')}"
                        f" intent={r.get('intent')!r}")
            for ev in self.learned:
                lines.append(f"- {ev}")
        return "\n".join(lines)

    def summary(self) -> dict:
        """Compact summary for feedback into a conversational planner."""
        failed = [s.skill for s in self.steps if not s.ok]
        status = "success" if self.steps and not failed else ("partial" if self.steps else "empty")
        return {
            "intent": self.intent, "recipe": self.recipe, "run_id": self.run_id,
            "status": status, "failed_skills": failed,
            "step_count": len(self.steps), "attempt": self.attempt,
        }


class ChipAgent:
    def __init__(self, skills_dir: str, mcp_command: list[str] | None = None,
                 db_path: str | None = None, planner=None,
                 extra_skills_dirs: list[str] | None = None,
                 experience_path: str | None = None):
        # built-in methodology skills ship with the package and are always on
        builtin = str(Path(__file__).parent / "skills")
        dirs = (extra_skills_dirs or []) + [builtin]
        self.registry = SkillRegistry(skills_dir, extra_dirs=dirs)
        self.mcp = McpAdapter(mcp_command)
        self.store = ReportStore(db_path) if db_path else None
        self.experience = ExperienceStore(experience_path) if experience_path else None
        self.planner = planner or KeywordPlanner()
        # plan/run share the store, experience file and the external MCP
        # adapter; the SDK server dispatches concurrent calls from worker
        # threads. plan() is lock-free (read-only); run() holds this lock
        # to serialize the external MCP adapter session and store/experience
        # writes (reentrant: run() calls _plan_impl() internally).
        self._op_lock = threading.RLock()
        self._env_fp: str | None | object = None   # None=unset, ""=unavailable

    # -- environment fingerprint (experience relevance) ----------------------
    def _env(self) -> str | None:
        """Cheap identity of the tool environment; None when unavailable.
        Experiences recorded under a different fingerprint are down-weighted
        at retrieval, so knowledge does not silently outlive tool upgrades."""
        if self._env_fp is None:
            try:
                import hashlib
                import sys as _sys
                from .eda_tools import discover
                disc = discover()
                bits = ["vcs:" + str(disc["tools"]["vcs"]["path"] or "none"),
                        "verdi:" + str(disc["tools"]["verdi"]["path"] or "none"),
                        "uvm:" + str(disc["uvm"]["default_home"])]
                fp = hashlib.sha1(
                    ("|".join(bits) + _sys.version.split()[0]).encode()).hexdigest()[:12]
            except Exception:
                fp = ""
            self._env_fp = fp
        return self._env_fp or None

    def plan(self, intent: str) -> dict:
        # lock-free: plan is read-only end-to-end (pure planner, read-only
        # registry/memory, store reads go through the WAL+locked sqlite
        # connection); serializing it under the run op-lock throttled the
        # hot path to one concurrent plan per process.
        return self._plan_impl(intent)

    def _plan_impl(self, intent: str) -> dict:
        decision = self.planner.plan(intent)
        key = decision["recipe"]
        recipe = RECIPES[key]
        if decision.get("steps"):
            # honour both the subset AND the LLM-requested order (the
            # planner prompt advertises reordering; it was silently dropped)
            by_skill = {s["skill"]: s for s in recipe["steps"]}
            steps = [by_skill[s] for s in decision["steps"] if s in by_skill]
        else:
            steps = list(recipe["steps"])
        # resolvable = in the skill registry (MCP/remote) OR a built-in local tool
        available = [s for s in steps
                     if s["skill"] in self.registry.skills or s["skill"] in LOCAL_TOOLS]
        missing = [s for s in steps
                   if s["skill"] not in self.registry.skills and s["skill"] not in LOCAL_TOOLS]
        plan = {"key": key, "title": recipe["title"], "steps": available,
                "missing": missing, "reason": decision.get("reason", "")}
        self._inject_domain_context(plan, intent)
        if self.experience:
            plan["past_experience"] = self.experience.search(
                intent, env_fp=self._env())
        self._inject_learning(plan)
        return plan

    def _inject_learning(self, plan: dict) -> None:
        """Feed run history back into planning: success replay, per-step
        stats, risk flags, run history (merged-retrieval tier 3), recipe
        regression guard and learned effective variants. Recipe order is
        NEVER reordered here — the pipeline gates (generate → compliance →
        simulate) are a contract; instead the decision layer (client model)
        receives the data."""
        if not self.store:
            return
        key = plan["key"]
        skills = {s["skill"] for s in plan["steps"]}
        # success-path replay: reuse the skill chain of the last green run
        succ = self.store.successful_runs(key, limit=1)
        if succ:
            plan["last_successful_run"] = {
                "run_id": succ[0]["id"], "intent": succ[0]["intent"],
                "skills": [s["skill"] for s in self.store.run_steps(succ[0]["id"])]}
        # per-step success stats (unfiltered) for the client's inspection
        rates = {sk: (cnt, ok) for sk, cnt, ok
                 in self.store.skill_success_rate(min_samples=1)}
        plan["step_stats"] = {
            sk: {"samples": cnt, "ok": ok, "rate": round(ok / cnt, 2) if cnt else None}
            for sk, (cnt, ok) in rates.items() if sk in skills}
        # risk list: proven high-failure skills (>=3 samples, <50% pass),
        # with their most common failure class
        fail_matrix = self.store.skill_failure_stats(min_samples=3)
        plan["risk"] = [
            {"skill": sk, "rate": round(ok / cnt, 2), "samples": cnt,
             "top_failure": fail_matrix.get(sk, [None])[0][0]}
            for sk, cnt, ok in self.store.skill_success_rate(min_samples=3)
            if sk in skills and ok / cnt < 0.5]
        # merged retrieval tier 3: the raw run trajectory for this recipe
        plan["run_history"] = self.store.recipe_runs(key, limit=5)
        # QoR-style guard: recent success-rate regression for this recipe
        trend = self.store.recipe_success_trend(key)
        if trend and trend["regression"]:
            plan["recipe_regression"] = trend
        # learned effective variants (domain-scoped, agent's own learning)
        domain = plan.get("domain")
        if domain:
            try:
                from .digital_memory import DomainMemory
                variants = DomainMemory(domain).plan_variants(key, limit=3)
                if variants:
                    plan["effective_variants"] = variants
            except Exception:
                _log.exception("plan variant replay failed (best-effort)")
        self._apply_replay(plan)

    def _apply_replay(self, plan: dict) -> None:
        """Recipe self-evolution: replay a proven-good skill ORDER when it is
        a permutation of the recipe's executable steps. The pipeline contract
        is preserved (every gate still runs — only the order is learned); the
        decision is auditable via plan["replay"] provenance."""
        available = plan["steps"]
        if not available:
            return
        skills = [s["skill"] for s in available]
        candidates = []
        for v in plan.get("effective_variants", []):
            v_skills = v.get("skills") or []
            if sorted(v_skills) == sorted(skills) and v_skills != skills:
                candidates.append((v.get("successes", 1), v))
        if candidates:
            candidates.sort(key=lambda c: -c[0])
            best = candidates[0][1]
            by_skill = {s["skill"]: s for s in available}
            plan["steps"] = [by_skill[s] for s in best["skills"] if s in by_skill]
            plan["replay"] = {"source": "effective_variant",
                              "run_id": best.get("run_id"),
                              "successes": best.get("successes"),
                              "order": best["skills"]}
            return
        lsr = plan.get("last_successful_run")
        if lsr and sorted(lsr["skills"]) == sorted(skills) and lsr["skills"] != skills:
            by_skill = {s["skill"]: s for s in available}
            plan["steps"] = [by_skill[s] for s in lsr["skills"] if s in by_skill]
            plan["replay"] = {"source": "last_successful_run",
                              "run_id": lsr["run_id"], "order": lsr["skills"]}

    def _inject_domain_context(self, plan: dict, intent: str) -> None:
        """Spec→tape-out alignment: when a plan maps to a digital-agents
        domain, inject its distilled knowledge + past domain experiences."""
        skills = ({s["skill"] for s in plan["steps"]}
                  | {s["skill"] for s in plan.get("missing", [])})
        domain = next((d for d, f in DOMAIN_FLOWS.items() if f.skill in skills),
                      None)
        if not domain:
            return
        plan["domain"] = domain
        plan["domain_stages"] = DOMAIN_FLOWS[domain].stages
        try:
            from .digital_memory import DomainMemory
            mem = DomainMemory(domain)
            plan["domain_knowledge_preview"] = mem.knowledge()[:800]
            plan["domain_experience"] = mem.search(intent, limit=3)
        except Exception as e:                      # memory is best-effort
            plan["domain_context_error"] = str(e)

    def run(self, intent: str, context: dict | None = None,
            progress_cb=None) -> RunReport:
        """Execute a planned run; optional progress_cb(i, total, skill_name)
        fires before each step (used by the SDK server for MCP progress)."""
        with self._op_lock:
            return self._run_impl(intent, context, progress_cb)

    def _run_impl(self, intent: str, context: dict | None,
                  progress_cb=None) -> RunReport:
        plan = self._plan_impl(intent)
        report = RunReport(intent=intent, recipe=plan["key"], title=plan["title"])
        if self.store:
            report.attempt = self.store.attempt_number(intent, plan["key"])
            prev = self.store.last_run(intent) if report.attempt > 1 else None
            if prev:
                report.reflections.insert(0, {
                    "previous_attempt": {
                        "run_id": prev["run_id"],
                        "failed_skills": prev["failed_skills"],
                        "recipe": prev["recipe"],
                        "recipe_drift": prev["recipe"] != plan["key"],
                    }})
        for i, step in enumerate(plan["steps"], 1):
            if progress_cb is not None:
                progress_cb(i, len(plan["steps"]), step["skill"])
            args = self._step_args(step, context)
            t0 = time.perf_counter()
            if step["skill"] in LOCAL_TOOLS:
                res = call_local(step["skill"], args)
            else:
                res = self.mcp.call(step["skill"], args)
            duration = time.perf_counter() - t0
            ok = "error" not in res
            detail = json.dumps(res, ensure_ascii=False)[:500]
            failure_class = classify_failure(detail) if not ok else None
            skill_meta = self.registry.skills.get(step["skill"])
            report.steps.append(StepResult(
                skill=step["skill"], why=step["why"], ok=ok,
                detail=detail,
                target=getattr(skill_meta, "target", None),
                failure_class=failure_class,
                retry_strategy=retry_strategy_for(failure_class) if failure_class else None,
                duration=round(duration, 3),
            ))
        if self.store:
            report.run_id = self.store.save(report)
        # reflect BEFORE recording this run: the search must learn from the
        # PAST, not echo the just-written record of the same run
        self._reflect(report, plan)          # failure -> similar past cases
        if self.experience:
            failed = [s for s in report.steps if not s.ok]
            detail = " ".join(s.detail for s in failed)
            failure_class = classify_failure(detail) if failed else "none"
            self.experience.add_if_new({**report.summary(),
                "failure_class": failure_class,
                "retry_strategy": retry_strategy_for(failure_class),
                "reason": plan["reason"]}, env_fp=self._env())
        self._record_success_variant(report, plan)
        self._maybe_auto_distill(plan, report)
        self._periodic_audit(report)
        observe = getattr(self.planner, "observe", None)
        if callable(observe):
            observe(report.summary())
        return report

    # -- proactive learning ---------------------------------------------------
    def _reflect(self, report: RunReport, plan: dict) -> None:
        """Failure reflection: attach similar past failures and their retry
        strategies, plus each failed skill's recurring failure classes, so
        the very next attempt starts from what was learned."""
        if not self.experience:
            return
        failed = [s for s in report.steps if not s.ok]
        if not failed:
            return
        query = " ".join(s.detail for s in failed)
        try:
            hits = self.experience.search(query, limit=3, env_fp=self._env())
        except Exception:
            hits = []
        for h in hits:
            rec = h["record"]
            if rec.get("failure_class", "none") == "none":
                continue
            report.reflections.append({
                "score": h["score"],
                "failure_class": rec.get("failure_class"),
                "retry_strategy": rec.get("retry_strategy"),
                "intent": rec.get("intent"),
            })
        # per-skill historical failure context (from the structured DB),
        # including the strategy that fixed each recurring class
        if self.store:
            matrix = self.store.skill_failure_strategies(min_samples=2)
            for s in failed:
                tops = matrix.get(s.skill)
                if tops:
                    report.reflections.append({
                        "skill": s.skill,
                        "historical_failures": [(fc, cnt) for fc, cnt, _ in tops],
                        "strategies": [strat for _, _, strat in tops],
                        "note": "该技能历史失败集中于以上类别, 优先排查"})

    def _record_success_variant(self, report: RunReport, plan: dict) -> None:
        """Persist a proven-good skill chain as an effective variant for the
        domain, so later plans can replay it (Layer 4: 有效步骤变体沉淀)."""
        domain = plan.get("domain")
        if not domain or any(not s.ok for s in report.steps):
            return
        try:
            from .digital_memory import DomainMemory
            DomainMemory(domain).record_plan_variant(
                recipe=plan["key"],
                skills=[s["skill"] for s in plan["steps"]],
                intent=report.intent, run_id=report.run_id)
        except Exception:
            _log.exception("success variant recording failed (best-effort)")

    def _periodic_audit(self, report: RunReport) -> None:
        """Periodic housekeeping inspection (Layer 5): every N runs, audit
        memory/DB health (read-only) and — only when explicitly enabled —
        run the data-quality cleaners."""
        if not self.store:
            return
        audit_every = int(os.environ.get("CHIP_AGENT_AUDIT_EVERY", "20"))
        try:
            if self.store.run_count() % audit_every != 0:
                return
            from .data_quality import audit_experience, audit_db
            notes = []
            if self.experience:
                notes.append(f"experience: {audit_experience(str(self.experience.path))}")
            notes.append(f"db: {audit_db(str(self.store.path))}")
            report.learned.append("巡检: " + " | ".join(notes))
            if os.environ.get("CHIP_AGENT_AUTO_CLEAN", "0") == "1":
                from .data_quality import clean_experience, clean_db
                if self.experience:
                    clean_experience(str(self.experience.path))
                clean_db(str(self.store.path))
                report.learned.append("巡检: 自动清洗完成 (CHIP_AGENT_AUTO_CLEAN=1)")
        except Exception:
            _log.exception("periodic audit failed (best-effort)")

    def _maybe_auto_distill(self, plan: dict, report: RunReport) -> None:
        """Recurring failures in a domain trigger an automatic knowledge
        distillation (memory-keeper) instead of waiting for a manual call."""
        domain = plan.get("domain")
        if not domain or os.environ.get("CHIP_AGENT_AUTO_DISTILL", "1") == "0":
            return
        if all(s.ok for s in report.steps):
            return
        try:
            from .digital_memory import DomainMemory
            mem = DomainMemory(domain)
            if len(mem.records()) >= AUTO_DISTILL_MIN_RECORDS:
                res = mem.distill(min_records=AUTO_DISTILL_MIN_RECORDS)
                if res.get("ok"):
                    report.learned.append(
                        f"自动蒸馏: domain '{domain}' 经验 {len(mem.records())} 条"
                        f" -> knowledge.md 已更新")
        except Exception:
            _log.exception("auto-distill failed (best-effort)")

    # keys each local tool actually consumes; anything else in the run
    # context is NOT broadcast to every downstream tool/MCP call
    LOCAL_TOOL_ARGS = {
        "generate_testbench": {"out_dir"},
        "check_uvm_compliance": {"root"},
        "check_eda_tools": set(),
        "run_simulation": {"root", "testname"},
        "open_waveform": {"fsdb", "signals"},
        "analyze_eda_log": {"log", "path", "kind"},
        "list_eda_wrappers": set(),
        "run_eda_wrapper": {"tool", "args", "timeout"},
        "design_state_pipeline": {
            "op", "id", "state", "created_by", "failure_class", "summary",
            "test_name", "module", "signal", "file", "expected", "observed",
            "waveform_path", "log_path", "fixed", "diff_summary", "files_changed"},
        "search_domain_memory": {"domain", "query", "limit", "memory_root", "add_record"},
        "memory_distill": {"domain", "memory_root", "min_records"},
        "memory_qor_trends": {"design", "domain", "memory_root"},
        "flow_guide": {"op", "phase", "intent"},
        # pynpi-backed waveform layer (fsdb/path interchangeable)
        "load_fsdb": {"fsdb", "path"},
        "get_active_fsdb": set(),
        "set_active_fsdb": {"fsdb"},
        "list_signals": {"fsdb", "path", "scope", "depth"},
        "list_signals_in_scope": {"fsdb", "path", "scope", "depth"},
        "get_signal_value_at_time": {"fsdb", "path", "signal", "time"},
        "get_first_value": {"fsdb", "path", "signal"},
        "get_last_value": {"fsdb", "path", "signal"},
        "find_signal_transition_to_value": {"fsdb", "path", "signal", "value",
                                            "time", "direction"},
        "find_signal_value_change_event": {"fsdb", "path", "signal", "time"},
        "find_nth_transition_of_signal": {"fsdb", "path", "signal", "n"},
        "calculate_signal_duration": {"fsdb", "path", "signal", "time"},
        "get_signal_switching_statistics": {"fsdb", "path", "signal"},
        "detect_unknown_and_get_previous_or_next_transitions":
            {"fsdb", "path", "signal", "time", "direction"},
        "detect_signal_sequence": {"fsdb", "path", "expression", "expr"},
        "get_max_latency": {"fsdb", "path", "signal_a", "signal", "signal_b"},
        "list_instances_in_hierarchy": {"fsdb", "path"},
        "show_hierarchy_tree": {"fsdb", "path"},
        "add_signals": {"fsdb", "path", "signals"},
        "read_specific_lines": {"path", "file", "start", "count"},
        "search_in_source_code_result": {"path", "file", "pattern", "query"},
    }

    def _step_args(self, step: dict, context: dict | None) -> dict:
        skill = step["skill"]
        ctx = context or {}
        if skill in self.LOCAL_TOOL_ARGS:
            allowed = self.LOCAL_TOOL_ARGS[skill]
            args = {k: v for k, v in ctx.items() if k in allowed}
        else:
            # remote MCP tool: forward the run context verbatim but never
            # leak agent-internal routing keys
            args = {k: v for k, v in ctx.items() if k != "skill"}
        args.setdefault("skill", skill)
        return args
