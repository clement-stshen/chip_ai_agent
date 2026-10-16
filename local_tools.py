"""Local (non-MCP) tools executed inside the agent process.

Implements the testbench generation loop mandated for the
"generate testbench" prompt:
  generate_testbench   -> copy the UVM 1800.2-2020.3.1 template project
  check_uvm_compliance -> MUST run after generation; FAIL blocks the report
                          step as ERR (IEEE 1800.2-2020 static rules)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .eda_log_analyzer import analyze_log, dvcon_queries, ug_step_queries
from .eda_tools import discover, open_verdi, run_simulation
from .design_state import DesignState, DEFAULT_STATE_PATH
from .digital_memory import DomainMemory, VALID_DOMAINS, qor_trends
from .flow_guide import (capabilities, overview, phase_detail, route_intent,
                         post_rtl_checklist)
from .npi_tools import (add_signals as npi_add_signals,
                        calculate_signal_duration,
                        detect_signal_sequence,
                        detect_unknown_and_get_previous_or_next_transitions,
                        find_nth_transition_of_signal,
                        find_signal_transition_to_value,
                        find_signal_value_change_event,
                        get_active_fsdb, get_first_value, get_last_value,
                        get_max_latency, get_signal_switching_statistics,
                        get_signal_value_at_time,
                        list_instances_in_hierarchy, list_signals,
                        list_signals_in_scope, load_fsdb_session,
                        read_specific_lines,
                        search_in_source_code_result,
                        set_active_fsdb, show_hierarchy_tree)

from .eda_tools import TEMPLATE_ROOT  # noqa: F401  (site_paths-backed)
SKILL_CHECKER = Path(__file__).parent / "skills" / "check_uvm_compliance" / "check_uvm_compliance.py"

_last_generated: str | None = None


def generate_testbench(args: dict) -> dict:
    global _last_generated
    out = args.get("out_dir") or tempfile.mkdtemp(prefix="uvm_tb_gen_")
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for sub in ("rtl", "tb"):
        src = TEMPLATE_ROOT / sub
        if not src.exists():
            return {"error": f"template missing: {src}", "ok": False}
        dst = out_path / sub
        shutil.copytree(src, dst, dirs_exist_ok=True)
        copied += sorted(str(p.relative_to(out_path)) for p in dst.glob("*.sv"))
    # sim/ (filelist + run script) so ready_command can run on the EDA host
    sim_src = TEMPLATE_ROOT / "sim"
    if sim_src.exists():
        sim_dst = out_path / "sim"
        sim_dst.mkdir(exist_ok=True)
        for name in ("filelist.f", "run_vcs.sh"):
            if (sim_src / name).exists():
                shutil.copy2(sim_src / name, sim_dst / name)
                copied.append(f"sim/{name}")
    shutil.copy2(TEMPLATE_ROOT / "check_uvm_compliance.py",
                 out_path / "check_uvm_compliance.py")
    _last_generated = str(out_path)
    return {
        "ok": True, "out_dir": str(out_path), "files": copied,
        "note": "UVM 1800.2-2020.3.1 template generated; "
                "compliance check MUST run next",
    }


def check_uvm_compliance(args: dict) -> dict:
    """Run the IEEE 1800.2-2020 static compliance check; never skipped."""
    root = args.get("root") or _last_generated
    if not root:
        return {"error": "no testbench generated yet (run generate_testbench first)",
                "ok": False}
    # prefer the self-contained checker bundled in the reusable skill
    checker = SKILL_CHECKER if SKILL_CHECKER.exists() else TEMPLATE_ROOT / "check_uvm_compliance.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(checker), str(root)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        return {"error": f"compliance check failed to run: {e}", "ok": False}
    out = (proc.stdout + proc.stderr).strip()
    ok = proc.returncode == 0 and "ALL CHECKS PASSED" in out
    result = {"ok": ok, "root": root, "check": "IEEE 1800.2-2020",
              "detail": out[-500:]}
    # agent marks a step ERR when "error" is present; include it on failure
    if not ok:
        result["error"] = "UVM IEEE 1800.2-2020 compliance check FAILED"
    return result


def check_eda_tools(args: dict) -> dict:
    """Discover VCS/Verdi/NPI availability (modulefile-aware)."""
    return {"ok": True, **discover()}


def run_sim(args: dict) -> dict:
    """Run a UVM simulation with VCS on the given project root.

    Accepts `out_dir` as an alias for `root`: generate_testbench reports
    its output as out_dir, and a run context carrying out_dir must land
    on the generated project instead of the template default.
    """
    root = args.get("root") or args.get("out_dir") or str(TEMPLATE_ROOT)
    extra = args.get("extra_args") or []
    if isinstance(extra, str):
        extra = [extra]
    return run_simulation(root, testname=args.get("testname", "fifo_smoke_test"),
                          timeout=int(args.get("timeout", 600)),
                          extra_args=extra)


def open_waveform(args: dict) -> dict:
    """Open an FSDB in Verdi (or return the ready command when unavailable)."""
    return open_verdi(args.get("fsdb", ""), args.get("signals"))


def analyze_eda_log(args: dict) -> dict:
    """Iteratively analyze an EDA log (VCS/UVM/Verdi/LSF) with classification."""
    path = args.get("log") or args.get("path")
    if not path:
        # default: most recent sim/comp log in the template project
        for cand in (TEMPLATE_ROOT / "sim/sim.log", TEMPLATE_ROOT / "sim/comp.log"):
            if cand.exists():
                path = str(cand)
                break
    if not path:
        return {"ok": False, "error": "no log path given and no default log found"}
    res = analyze_log(path, kind=args.get("kind"))
    # Failed runs: attach step-level UG manual guidance when the vector
    # index is available. Degrade gracefully when it is not built.
    if res.get("ok") and res.get("verdict") != "PASS" and res.get("failure_class"):
        try:
            from . import ug_index
            if ug_index._load(ug_index._ug_root()) is not None:
                queries = ug_step_queries(res.get("kind"), res.get("failure_class"))
                manual = []
                for q in queries:
                    sr = ug_index.search(q, kind="steps", top_k=3)
                    manual.append({"query": q, "hits": sr.get("hits", [])})
                if manual:
                    res["manual_steps"] = manual
        except Exception as exc:  # noqa: BLE001 — guidance must never break analysis
            res.setdefault("notes", []).append(f"manual step lookup skipped: {exc}")
        # Cross-domain closed loop: recommend DVCon 2025/2026 paper methods
        # for the same failure class. The seed index builds itself from the
        # shipped corpus, so this degrades to an empty list, never an error.
        try:
            from . import dvcon_index
            methods = []
            for q in dvcon_queries(res.get("kind"), res.get("failure_class")):
                sr = dvcon_index.search(q, top_k=2)
                hits = sr.get("hits", [])
                if hits:
                    methods.append({
                        "query": q, "failure_class": res.get("failure_class"),
                        "papers": [{"title": h["title"], "authors": h["authors"],
                                    "year": h["year"], "venue": h["venue"],
                                    "excerpt": h["excerpt"]} for h in hits]})
            if methods:
                res["dvcon_methods"] = methods
                # opt-in persistent learning: keep the failure_class -> paper
                # method mapping in domain memory so the next run of the same
                # failure class recalls it without re-searching the corpus.
                if args.get("learn"):
                    try:
                        from .digital_memory import DomainMemory
                        fc = res.get("failure_class") or "unknown"
                        titles = [p["title"]
                                  for m in methods for p in m["papers"]]
                        rec = DomainMemory("verification").upsert({
                            "run_id": f"dvcon-methods-{fc}",
                            "tool_used": "chip_analyze_eda_log",
                            "issues_encountered": [f"failure_class={fc}"],
                            "fixes_applied": titles,
                            "notes": "DVCon 2025/2026 paper methods for "
                                     + "; ".join(m["query"] for m in methods),
                        })
                        res["memory_record"] = rec.get("run_id")
                    except Exception as exc:  # noqa: BLE001
                        res.setdefault("notes", []).append(
                            f"dvcon memory persist skipped: {exc}")
        except Exception as exc:  # noqa: BLE001
            res.setdefault("notes", []).append(f"dvcon method lookup skipped: {exc}")
    return res


def design_state_op(args: dict) -> dict:
    """fix_request closed-loop operations (see design_state.py)."""
    op = args.get("op", "summary")
    st = DesignState(args.get("state") or DEFAULT_STATE_PATH)
    if op == "summary":
        return {"ok": True, **st.summary()}
    if op == "next":
        st.ensure_session()
        act = st.next_pipeline_action()
        st.save()
        return {"ok": True, **act}
    if op == "open":
        fr = st.open_fix_request(
            created_by=args.get("created_by", "chip_agent"),
            failure_class=args["failure_class"],
            summary=args["summary"], test_name=args.get("test_name", ""),
            module=args.get("module", ""), signal=args.get("signal"),
            file=args.get("file"), expected=args.get("expected"),
            observed=args.get("observed"),
            waveform_path=args.get("waveform_path"),
            log_path=args.get("log_path"))
        st.save()
        return {"ok": True, "fix_request": fr}
    if op == "claim":
        fr = st.claim(args["id"]); st.save()
        return {"ok": True, "fix_request": fr}
    if op == "close":
        fr = st.close_fix_request(
            args["id"], fixed=bool(args.get("fixed", True)),
            diff_summary=args.get("diff_summary", ""),
            files_changed=args.get("files_changed"))
        st.save()
        return {"ok": True, "fix_request": fr}
    if op == "archive":
        ids = st.archive_resolved(); st.save()
        return {"ok": True, "archived": ids}
    return {"ok": False, "error": f"unknown op: {op} "
            "(summary|next|open|claim|close|archive)"}


def search_domain_memory(args: dict) -> dict:
    """TF-IDF search over a domain's experiences.jsonl + knowledge preview."""
    domain = args.get("domain", "verification")
    try:
        mem = DomainMemory(domain, root=args.get("memory_root"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if args.get("add_record"):
        rec = mem.upsert(args["add_record"])
        return {"ok": True, "upserted": rec.get("run_id"), "record": rec}
    hits = mem.search(args.get("query", ""), limit=int(args.get("limit", 5)))
    return {"ok": True, "domain": domain, "root": str(mem.root),
            "results": hits,
            "knowledge_preview": mem.knowledge()[:600]}


def memory_distill(args: dict) -> dict:
    try:
        mem = DomainMemory(args.get("domain", "verification"),
                           root=args.get("memory_root"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return mem.distill(min_records=int(args.get("min_records", 10)))


def memory_qor_trends(args: dict) -> dict:
    design = args.get("design", "")
    if not design:
        return {"ok": False, "error": "design is required"}
    return qor_trends(design, domain=args.get("domain"),
                      root=args.get("memory_root"))


def flow_guide(args: dict) -> dict:
    """前端RTL→综合→后端→Signoff 深度流程知识 (阶段/产物/门/反馈环/坑)。"""
    op = args.get("op", "overview")
    if op == "overview":
        return {"ok": True, "phases": overview()}
    if op == "phase":
        try:
            return {"ok": True, **phase_detail(args.get("phase", ""))}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
    if op == "route":
        return {"ok": True, **route_intent(args.get("intent", ""))}
    if op == "capabilities":
        return {"ok": True, "capabilities": capabilities()}
    if op == "post_rtl_checklist":
        return {"ok": True, "post_rtl_checklist": post_rtl_checklist()}
    return {"ok": False,
            "error": f"unknown op: {op} "
                     "(overview|phase|route|capabilities|post_rtl_checklist)"}


LOCAL_TOOLS = {
    "generate_testbench": generate_testbench,
    "check_uvm_compliance": check_uvm_compliance,
    "check_eda_tools": check_eda_tools,
    "run_simulation": run_sim,
    "open_waveform": open_waveform,
    "analyze_eda_log": analyze_eda_log,
    "design_state_pipeline": design_state_op,
    "search_domain_memory": search_domain_memory,
    "memory_distill": memory_distill,
    "memory_qor_trends": memory_qor_trends,
    "flow_guide": flow_guide,
    # -- pynpi-backed waveform execution layer (real Verdi required; every
    #    tool degrades gracefully with setup instructions otherwise)
    "load_fsdb": load_fsdb_session,
    "get_active_fsdb": get_active_fsdb,
    "set_active_fsdb": set_active_fsdb,
    "list_signals": list_signals,
    "list_signals_in_scope": list_signals_in_scope,
    "get_signal_value_at_time": get_signal_value_at_time,
    "get_first_value": get_first_value,
    "get_last_value": get_last_value,
    "find_signal_transition_to_value": find_signal_transition_to_value,
    "find_signal_value_change_event": find_signal_value_change_event,
    "find_nth_transition_of_signal": find_nth_transition_of_signal,
    "calculate_signal_duration": calculate_signal_duration,
    "get_signal_switching_statistics": get_signal_switching_statistics,
    "detect_unknown_and_get_previous_or_next_transitions":
        detect_unknown_and_get_previous_or_next_transitions,
    "detect_signal_sequence": detect_signal_sequence,
    "get_max_latency": get_max_latency,
    "list_instances_in_hierarchy": list_instances_in_hierarchy,
    "show_hierarchy_tree": show_hierarchy_tree,
    "add_signals": npi_add_signals,
    "read_specific_lines": read_specific_lines,
    "search_in_source_code_result": search_in_source_code_result,
}


def call_local(skill: str, args: dict) -> dict:
    fn = LOCAL_TOOLS.get(skill)
    if fn is None:
        return {"error": f"unknown local tool: {skill}"}
    return fn(args)
