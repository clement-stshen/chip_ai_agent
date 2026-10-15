"""Verification stage pipeline, ported from digital-chip-design-agents
verification-orchestrator: 8 stages, deterministic loop-back rules with
per-row caps, and escalation with full state when caps are exhausted.
"""

from __future__ import annotations

from .failure_taxonomy import classify_failure, retry_strategy_for

VERIFICATION_STAGES = [
    "tb_architecture", "test_planning", "uvm_tb_build", "directed_tests",
    "constrained_random", "coverage_analysis", "formal_assist",
    "regression_signoff",
]

# (stage, on_failure_class) -> (goto_stage, max_retries)   [loop-back table]
LOOP_BACKS: dict[tuple[str, str], tuple[str, int]] = {
    ("uvm_tb_build", "tool_error"): ("uvm_tb_build", 3),
    ("uvm_tb_build", "functional"): ("uvm_tb_build", 3),
    ("coverage_analysis", "coverage_gap"): ("constrained_random", 5),
    ("regression_signoff", "functional"): ("constrained_random", 3),
}

# DUT bug found in directed_tests is never looped locally -> escalate
ESCALATE_ON = {("directed_tests", "functional"): "fix_request hand-off to pipeline-orchestrator"}


class StageResult(dict):
    """{stage, status: PASS|FAIL|WARN, failure_class, issues: [...]}"""


def _normalize(raw: dict, stage: str) -> StageResult:
    status = str(raw.get("status", "FAIL")).strip().upper()
    if status not in ("PASS", "FAIL", "WARN"):
        status = "FAIL"
        raw = {**raw, "failure_class": raw.get("failure_class") or "tool_error"}
    failure_class = raw.get("failure_class")
    if status != "PASS" and not failure_class:
        failure_class = classify_failure(str(raw.get("issues") or raw.get("detail") or ""))
    return StageResult(stage=stage, status=status,
                       failure_class=failure_class or "none",
                       issues=raw.get("issues", []))


class VerificationPipeline:
    """Run the 8-stage UVM flow through a caller-provided stage executor.

    executor(stage: str, attempt: int) -> dict with at least {"status": ...}.
    Loop-backs are applied per the ported table; caps trigger escalation with
    full stage state (stage, attempts, last QoR, suspected root cause).
    """

    def __init__(self, executor):
        self.executor = executor
        self.trace: list[StageResult] = []

    def run(self) -> dict:
        i = 0
        attempts: dict[str, int] = {}
        while i < len(VERIFICATION_STAGES):
            stage = VERIFICATION_STAGES[i]
            attempts[stage] = attempts.get(stage, 0) + 1
            res = _normalize(self.executor(stage, attempts[stage]), stage)
            self.trace.append(res)
            if res["status"] == "PASS":
                i += 1
                continue
            cls = res["failure_class"]
            if (stage, cls) in ESCALATE_ON:
                return self._terminate(res, attempts, ESCALATE_ON[(stage, cls)])
            goto, cap = LOOP_BACKS.get((stage, cls), (None, 0))
            if goto is None:
                return self._terminate(res, attempts, "no loop-back rule for this failure class")
            if attempts[stage] > cap:
                return self._terminate(res, attempts,
                    f"loop cap {cap}x exhausted at {stage}")
            i = VERIFICATION_STAGES.index(goto)  # loop back
        return {"decision": "signoff", "attempts": attempts, "trace": self.trace}

    def _terminate(self, res: StageResult, attempts: dict, reason: str) -> dict:
        return {"decision": "escalate", "reason": reason,
                "failed_stage": res["stage"],
                "failure_class": res["failure_class"],
                "retry_strategy": retry_strategy_for(res["failure_class"]),
                "attempts": attempts, "trace": self.trace}
