"""Failure classification & retry strategy, ported from the
digital-chip-design-agents pipeline-orchestration skill (authoritative mapping).
"""

FAILURE_CLASS_MAP: dict[str, str] = {
    "none": "none",            # no failure
    "functional": "refine",    # re-run with failing test + waveform
    "timing": "refine",        # re-run optimisation targeting failing paths
    "power_area": "refine",    # re-run targeting budget overage
    "coverage_gap": "refine",  # add targeted stimulus to close holes
    "connectivity": "refine",  # re-run targeting violated interface
    "drc_lvs": "regenerate",   # re-run place/route from clean state
    "tool_error": "regenerate",# re-run same stage from scratch
    "spec_gap": "escalate",    # ambiguous/missing spec, needs user
    "resource_limit": "escalate",  # cap hit, human decision
}

# keyword hints for coarse auto-classification from free text (logs, errors)
_CLASSIFY_HINTS: list[tuple[str, str]] = [
    ("coverage", "coverage_gap"),
    ("uncovered", "coverage_gap"),
    ("miscompare", "functional"),
    ("mismatch", "functional"),          # real log vocabulary (was miscompare-only)
    ("uvm_fatal", "functional"),
    ("uvm_error", "functional"),         # severity is part of classify input
    ("timeout", "functional"),           # objection/phase timeout -> refine, not regenerate
    ("objection", "functional"),
    ("scoreboard", "functional"),
    ("assertion failed", "functional"),
    ("setup", "timing"),
    ("setup violation", "timing"),
    ("hold", "timing"),
    ("hold violation", "timing"),
    ("violated interface", "connectivity"),
    ("connectivity", "connectivity"),
    ("drc", "drc_lvs"),
    ("lvs", "drc_lvs"),
    ("license", "tool_error"),
    ("licence", "tool_error"),
    ("cannot open", "tool_error"),
    ("compilation error", "tool_error"),
    ("ambiguous", "spec_gap"),
    ("incomplete spec", "spec_gap"),
    ("iteration cap", "resource_limit"),
    ("budget exhausted", "resource_limit"),
    ("memlimit", "resource_limit"),
    ("runlimit", "resource_limit"),
    ("killed by lsf", "resource_limit"),
    ("out of memory", "resource_limit"),
]


def retry_strategy_for(failure_class: str) -> str:
    return FAILURE_CLASS_MAP.get(failure_class, "escalate")


def classify_failure(text: str) -> str:
    """Coarse keyword-based classification; returns a failure_class enum value."""
    t = (text or "").lower()
    for hint, cls in _CLASSIFY_HINTS:
        if hint in t:
            return cls
    return "tool_error"
