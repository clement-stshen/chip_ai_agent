"""spec→tape-out pipeline engine aligned with digital-chip-design-agents.

Three layers, all code-enforced:
  1. DomainFlowRunner — one domain's stages with loop-back caps, reporting
     contract, checkpoint human gate at the sign-off stage, design_state
     history[] trace, and two-tier memory recording.
  2. PipelineRunner   — spec→tape-out mainline ordering with branch domains;
     every design domain emits a fix_request on DUT-bug escalation instead
     of looping locally.
  3. CrossDomainDriver — the verification↔RTL closed loop: dispatch →
     re-verify → iteration cap → divergence → archive (design_state.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .domain_flows import DOMAIN_FLOWS, MAINLINE, BRANCHES, flow
from .design_state import DesignState
from .digital_memory import DomainMemory
from .reporting import StageReport, Gate, ContractViolation

StageExecutor = Callable[[str, str, int], dict]
"""executor(domain, stage, attempt) -> stage dict:
   {status, confidence?, failure_class?, qor?, issues?, evidence?, gates?}
   where gates = [{name, passed(bool|None), evidence, criterion?}]"""


_GATE_UNITS = ("ns", "ps", "pct", "mv", "um2", "kb", "mhz")


def _norm_gate(name: str) -> str:
    """Alphanumeric taxonomy key for one gate name."""
    normalized = name.lower()
    return "".join(ch for ch in normalized if ch.isalnum())


def _gate_variants(name: str) -> set[str]:
    """Accepted taxonomy keys for one expected gate: exact form plus the
    unit-suffix-dropped variant ('wns_ns' also accepts 'wns'). Directional:
    the reported name never strips its own suffix, so 'drc_violations'
    never collides with a 'ns'-suffixed stem."""
    variants = {_norm_gate(name)}
    key = _norm_gate(name)
    for unit in _GATE_UNITS:
        suffix = "_" + unit
        if name.lower().endswith(suffix):
            variants.add(_norm_gate(name.lower()[:-len(suffix)]))
            break
    return variants


def _gate_taxonomy_diagnostics(
        reported: list[str], expected: dict[str, str]) -> list[str]:
    """Step 22 gate-naming audit: explain why a reported gate never matched
    a signoff gate. Fail-closed semantics are unchanged; this only turns a
    silent 'unmeasured' into an actionable root-cause hint."""
    diags: list[str] = []
    expected_variants = {n: _gate_variants(n) for n in expected}
    for name in reported:
        if name in expected or name.startswith("wrapper:"):
            continue
        match = None
        for n, vs in expected_variants.items():
            if _norm_gate(name) in vs:
                match = n
                break
        if match:
            diags.append(
                f"gate name mismatch: reported '{name}' matches expected "
                f"'{match}' only after unit-suffix normalization — "
                f"rename to '{match}'")
        else:
            diags.append(
                f"unmatched reported gate '{name}' (intermediate/wrapper "
                f"gates do not satisfy signoff)")
    return diags


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunTrace:
    stage: str
    attempt: int
    status: str
    failure_class: str
    retry_strategy: str
    suggested_next_step: str
    reason: str = ""


@dataclass
class DomainRunResult:
    domain: str
    decision: str                       # signoff | escalate | await_approval
    trace: list[RunTrace] = field(default_factory=list)
    signoff: bool = False
    reason: str = ""
    fix_request_id: str | None = None

    def to_dict(self) -> dict:
        return {"domain": self.domain, "decision": self.decision,
                "signoff": self.signoff, "reason": self.reason,
                "fix_request_id": self.fix_request_id,
                "trace": [t.__dict__ for t in self.trace]}


class DomainFlowRunner:
    """Execute one domain's flow with code-enforced loop-backs and gates."""

    def __init__(self, domain: str, executor: StageExecutor,
                 state: DesignState, memory_root=None):
        self.flow = flow(domain)
        self.domain = domain
        self.executor = executor
        self.state = state
        self.memory = DomainMemory(domain, root=memory_root)

    def run(self, fix_request_id: str | None = None) -> DomainRunResult:
        stages = self.flow.stages
        attempts: dict[str, int] = {}
        i = 0
        trace: list[RunTrace] = []
        gate_results = {}
        while i < len(stages):
            stage = stages[i]
            attempts[stage] = attempts.get(stage, 0) + 1
            try:
                rep = self._normalize(self.executor(self.domain, stage,
                                                    attempts[stage]), stage)
            except ContractViolation:
                raise
            except Exception as e:                    # executor crash -> FAIL
                rep = StageReport(stage=stage, status="FAIL",
                                  failure_class="tool_error",
                                  evidence=str(e))
            trace.append(RunTrace(
                stage=stage, attempt=attempts[stage], status=rep.status,
                failure_class=rep.failure_class,
                retry_strategy=rep.retry_strategy,
                suggested_next_step=("proceed" if rep.status == "PASS"
                                     else f"loop_back:{rep.retry_strategy}"),
                reason=rep.notes))
            self._history_entry(rep, fix_request_id)
            expected_gates = {
                _norm_gate(name): name for name in self.flow.signoff_gates}
            for gate in rep.gates:
                expected_name = expected_gates.get(_norm_gate(gate.name))
                if expected_name and expected_name != gate.name:
                    gate_results.pop(expected_name, None)
                gate_results[gate.name] = gate

            if rep.status == "PASS":
                i += 1
                continue

            # DUT bug escalations: fix_request hand-off, never local retry
            for esc in self.flow.escalations:
                if esc.stage == stage and esc.fix_request:
                    if rep.failure_class == esc.failure_class:
                        return self._fix_request_escalation(
                            rep, trace, fix_request_id)
                if esc.stage == stage and not esc.fix_request:
                    if rep.failure_class == esc.failure_class:
                        result = DomainRunResult(
                            self.domain, "escalate", trace, False,
                            f"{stage}: {esc.trigger}")
                        self._record_experience(trace, signoff=False,
                                                note=result.reason)
                        return result

            lb = self.flow.loop_back_for(stage, rep.failure_class)
            if lb is None:
                result = DomainRunResult(
                    self.domain, "escalate", trace, False,
                    f"no loop-back rule for ({stage}, {rep.failure_class})")
                self._record_experience(trace, signoff=False, note=result.reason)
                return result
            if lb.cap >= 0 and attempts[stage] > lb.cap:
                result = DomainRunResult(
                    self.domain, "escalate", trace, False,
                    f"loop cap {lb.cap}x exhausted at {stage} "
                    f"({rep.failure_class}; last: {rep.notes or rep.failure_class}) "
                    f"— relax/supply/accept required")
                self._record_experience(trace, signoff=False, note=result.reason)
                return result
            i = stages.index(lb.goto)

        return self._signoff_gate(trace, fix_request_id, gate_results)

    # -- helpers ---------------------------------------------------------------
    def _normalize(self, raw: dict, stage: str) -> StageReport:
        gates = [Gate(name=g.get("name", f"gate_{j}"),
                      passed=g.get("passed"), evidence=g.get("evidence", ""),
                      criterion=g.get("criterion", ""),
                      inferred=g.get("inferred", False))
                 for j, g in enumerate(raw.get("gates", []))]
        return StageReport(
            stage=stage,
            status=raw.get("status", "FAIL"),
            confidence=raw.get("confidence", "high"),
            failure_class=(raw.get("failure_class") or
                           ("none" if raw.get("status") == "PASS"
                            else "tool_error")),
            qor=raw.get("qor", {}), issues=raw.get("issues", []),
            gates=gates, evidence=raw.get("evidence", ""),
            notes=raw.get("notes", ""))

    def _history_entry(self, rep: StageReport, fr_id: str | None) -> None:
        self.state.data["history"].append({
            "timestamp": _now(), "domain": self.domain,
            "stage": rep.stage, "status": rep.status,
            "confidence": rep.confidence,
            "failure_class": rep.failure_class,
            "retry_strategy": rep.retry_strategy,
            "suggested_next_step": ("proceed" if rep.status == "PASS"
                                    else "loop_back"),
            "reason": rep.notes, "fix_request_id": fr_id,
        })

    def _fix_request_escalation(self, rep: StageReport, trace: list[RunTrace],
                                fr_id: str | None) -> DomainRunResult:
        if fr_id:      # servicing an existing request: verdict is the re-run
            ok = rep.status == "PASS"
            return DomainRunResult(self.domain, "signoff" if ok else "escalate",
                                   trace, ok,
                                   f"re-verification of {fr_id}: "
                                   f"{'PASS' if ok else 'FAIL'}", fr_id)
        fr = self.state.open_fix_request(
            created_by=(f"{self.domain}-orchestrator"
                        if self.domain in ("verification", "formal")
                        else "chip_agent"),
            failure_class={"verification": "functional",
                           "formal": "formal_cex"}.get(self.domain,
                                                       "functional"),
            summary=rep.notes or f"{self.domain}/{rep.stage} DUT bug",
            test_name=rep.stage,
            module=rep.qor.get("module", ""))
        fr["origin_domain"] = self.domain
        self.state.save()
        self._record_experience(trace, signoff=False,
                                note=f"fix_request {fr['id']} opened")
        return DomainRunResult(self.domain, "escalate", trace, False,
                               f"DUT bug at {rep.stage} — fix_request "
                               f"{fr['id']} opened, pipeline-orchestrator owns "
                               f"RTL dispatch", fr["id"])

    def _signoff_gate(self, trace: list[RunTrace], fr_id: str | None,
                      gate_results: dict) -> DomainRunResult:
        missing = []
        failed = []
        for name in self.flow.signoff_gates:
            gate = gate_results.get(name)
            if gate is None:
                missing.append(name)
            elif gate.passed is not True or gate.inferred:
                failed.append(name)
        if missing or failed:
            details = []
            if missing:
                details.append("unmeasured: " + ", ".join(missing))
            if failed:
                details.append("not measured-PASS: " + ", ".join(failed))
            diags = _gate_taxonomy_diagnostics(
                list(gate_results), self.flow.signoff_gates)
            if diags:
                details.extend(diags)
            reason = "signoff gates incomplete (" + "; ".join(details) + ")"
            self._record_experience(trace, signoff=False, note=reason)
            return DomainRunResult(self.domain, "escalate", trace, False, reason)

        ckpt = self.flow.checkpoint_stage
        checkpoints = self.state.data.get("pipeline_config", {}).get(
            "checkpoints", [])
        approved = {a.get("stage") for a in
                    self.state.data.get("approved_checkpoints", [])}
        if ckpt and ckpt in checkpoints and ckpt not in approved:
            self.state.data["pending_approval"] = {
                "type": "checkpoint", "stage": ckpt,
                "agent": f"{self.domain}-orchestrator",
                "reason": f"checkpoint {ckpt} requires human approval",
                "fix_request_id": fr_id, "requires_user": True}
            self.state.data["history"].append({
                "timestamp": _now(), "domain": self.domain, "stage": ckpt,
                "decision": "await_approval", "confidence": "high",
                "failure_class": "none", "retry_strategy": "none",
                "suggested_next_step": "escalate",
                "reason": self.state.data["pending_approval"]["reason"]})
            self.state.save()
            self._record_experience(trace, signoff=False,
                                    note=f"awaiting checkpoint {ckpt}")
            return DomainRunResult(self.domain, "await_approval", trace, False,
                                   f"checkpoint {ckpt} awaiting human approval")
        self.state.data.setdefault(f"{self.domain}_status", {})[
            "signoff"] = True
        self.state.data["history"].append({
            "timestamp": _now(), "domain": self.domain, "stage": ckpt,
            "decision": "signoff", "confidence": "high",
            "failure_class": "none", "retry_strategy": "none",
            "suggested_next_step": "proceed",
            "reason": f"{self.domain} all sign-off gates measured-PASS"})
        self.state.save()
        self._record_experience(trace, signoff=True, note="all gates PASS")
        return DomainRunResult(self.domain, "signoff", trace, True,
                               f"{self.domain} signoff")

    def _record_experience(self, trace: list[RunTrace], *, signoff: bool,
                           note: str) -> None:
        rid = f"{self.domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.memory.upsert({
            "run_id": rid, "timestamp": _now(), "domain": self.domain,
            "design_name": self.state.data.get("design_name"),
            "tool_used": self.flow.vendor_tool or self.flow.skill,
            "stages_completed": [t.stage for t in trace if t.status == "PASS"],
            "loop_backs": {t.stage: t.attempt for t in trace if t.attempt > 1},
            "key_metrics": {}, "issues_encountered": [
                f"{t.stage}:{t.failure_class}" for t in trace
                if t.status != "PASS"],
            "fixes_applied": [], "signoff_achieved": signoff, "notes": note})


class PipelineRunner:
    """spec→tape-out mainline + branches, driven through DomainFlowRunner."""

    def __init__(self, executor: StageExecutor, state: DesignState,
                 domains: list[str] | None = None, memory_root=None):
        self.executor = executor
        self.state = state
        self.memory_root = memory_root
        order: list[str] = []
        for d in MAINLINE:
            order.append(d)
            for b in BRANCHES.get(d, []):
                order.append(b)
        self.domains = domains or [d for d in order if d in DOMAIN_FLOWS]

    def run(self) -> dict:
        self.state.ensure_session()
        results: list[DomainRunResult] = []
        for d in self.domains:
            res = DomainFlowRunner(d, self.executor, self.state,
                                   self.memory_root).run()
            results.append(res)
            if res.decision in ("escalate", "await_approval"):
                break
        all_signoff = (all(r.signoff for r in results)
                       and len(results) == len(self.domains))
        if all_signoff:
            self.state.archive_resolved()
        self.state.save()
        return {"decision": "signoff" if all_signoff else results[-1].decision,
                "domains_run": [r.domain for r in results],
                "results": [r.to_dict() for r in results],
                "pipeline_session_id": self.state.data.get("pipeline_session_id")}


class CrossDomainDriver:
    """verification↔RTL closed loop driver (pipeline-orchestrator role).

    step()      -> next deterministic action from design_state
    re_verify() -> run the originating domain against a serviced fix_request
    """

    def __init__(self, state: DesignState, executor: StageExecutor,
                 memory_root=None):
        self.state = state
        self.executor = executor
        self.memory_root = memory_root

    def step(self) -> dict:
        self.state.ensure_session()
        act = self.state.next_pipeline_action()
        self.state.save()
        return act

    def re_verify(self, fr_id: str) -> dict:
        fr = next((f for f in self.state.data["fix_requests"]
                   + self.state.data.get("archive_fix_requests", [])
                   if f["id"] == fr_id), None)
        if fr is None:
            return {"ok": False, "error": f"fix_request not found: {fr_id}"}
        if fr["status"] != "fixed":
            return {"ok": False,
                    "error": f"fix_request {fr_id} is {fr['status']}; "
                             "RTL must close it as fixed before re-verify"}
        domain = fr["created_by"].replace("-orchestrator", "")
        domain = fr.get("origin_domain", domain)
        if domain not in DOMAIN_FLOWS:
            domain = "verification"
        res = DomainFlowRunner(domain, self.executor, self.state,
                               self.memory_root).run(fix_request_id=fr_id)
        self.state.save()
        return {"ok": True, "re_verified": fr_id, "domain": domain,
                **res.to_dict()}
