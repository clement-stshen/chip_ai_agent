"""Reporting Contract, code-enforced (vendored agent_shared_sections.md).

Rules:
  1. exit 0 / empty output / verified=false is NOT a pass
  2. a gate that was not run reports NOT RUN (passed=None), never PASS
  3. measured evidence is separate from inference
  4. every FAIL/WARN carries failure_class + mapped retry_strategy
  5. signoff is true only when every declared gate is measured-PASS
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .failure_taxonomy import retry_strategy_for

STATUSES = ("PASS", "FAIL", "WARN")
CONFIDENCES = ("high", "medium", "low")


class ContractViolation(ValueError):
    pass


@dataclass
class Gate:
    name: str
    passed: bool | None                 # None = NOT RUN / unverified
    evidence: str = ""                  # measured source (command/file/line)
    criterion: str = ""                 # what "pass" means
    inferred: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name,
                "status": ("PASS" if self.passed else
                           "FAIL" if self.passed is False else "NOT RUN"),
                "measured": not self.inferred,
                "evidence": self.evidence, "criterion": self.criterion}


@dataclass
class StageReport:
    stage: str
    status: str                          # PASS | FAIL | WARN
    confidence: str = "high"
    failure_class: str = "none"
    qor: dict[str, Any] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    gates: list[Gate] = field(default_factory=list)
    evidence: str = ""                   # raw command output / wrapper JSON
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ContractViolation(f"status must be one of {STATUSES}")
        if self.confidence not in CONFIDENCES:
            raise ContractViolation(
                f"confidence must be one of {CONFIDENCES}")
        if self.status in ("FAIL", "WARN"):
            if self.failure_class in ("", "none"):
                raise ContractViolation(
                    f"{self.stage}: {self.status} requires a non-none "
                    "failure_class (Reporting Contract #4)")

    @property
    def retry_strategy(self) -> str:
        return retry_strategy_for(self.failure_class)

    def signoff_ok(self) -> bool:
        """True only when all gates are measured-PASS (never NOT RUN)."""
        return bool(self.gates) and all(
            g.passed is True and not g.inferred for g in self.gates)

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "status": self.status,
            "confidence": self.confidence,
            "failure_class": self.failure_class,
            "retry_strategy": self.retry_strategy,
            "qor": self.qor, "issues": self.issues,
            "gates": [g.to_dict() for g in self.gates],
            "evidence_excerpt": self.evidence[-500:],
            "notes": self.notes,
            "suggested_next_step": ("proceed" if self.status == "PASS"
                                    else f"loop_back (retry={self.retry_strategy})"),
        }


def gate_from_wrapper(wrapper_result: dict, name: str = "") -> Gate:
    """Build a Gate from a vendored wrapper JSON result.

    Contract #1: exit_code 0 with status FAIL / verified=false / unparsable
    output is never a pass — verified=True is the only measured pass.
    """
    name = name or wrapper_result.get("tool", "wrapper")
    verified = wrapper_result.get("verified") is True
    status = wrapper_result.get("status", "")
    return Gate(
        name=name,
        passed=True if verified else (False if status in ("FAIL", "WARN") else None),
        evidence=f"wrapper status={status} exit={wrapper_result.get('exit_code')} "
                 f"errors={len(wrapper_result.get('errors', []))}",
        criterion="wrapper verified=true (tool's own pass marker)")
