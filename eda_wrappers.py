"""Run the vendored digital-chip-design-agents EDA wrapper scripts.

Wrappers execute a tool, compress its 10k-50k line log into compact JSON
(status/verified/summary/errors/warnings) and enforce the reporting
contract: exit 0 alone is never a pass — the tool's own pass marker is
required. This module launches them with a bash fallback (upstream ships
them without the execute bit) and a hard FAIL on any launch problem.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

WRAPPERS_DIR = (Path(__file__).resolve().parent / "digital" /
                "plugins" / "infrastructure" / "tools")

WRAPPERS: dict[str, str] = {
    "verilator-sim": "wrap-verilator-sim.sh",
    "yosys": "wrap-yosys.sh",
    "openroad": "wrap-openroad.sh",
    "opensta": "wrap-opensta.sh",
    "klayout": "wrap-klayout.sh",
    "symbiflow": "wrap-symbiflow.sh",
    "bambu": "wrap-bambu.sh",
    "gem5": "wrap-gem5.sh",
}

VALID_STATUSES = ("PASS", "WARN", "FAIL")


def list_wrappers() -> list[dict]:
    out = []
    for tool, rel in WRAPPERS.items():
        p = WRAPPERS_DIR / rel
        out.append({"tool": tool, "path": str(p),
                    "exists": p.exists(),
                    "executable": os.access(p, os.X_OK) if p.exists() else False})
    return out


def run_wrapper(tool: str, args: list[str] | None = None,
                timeout: int = 300) -> dict:
    """Run one wrapper; always returns the wrapper JSON contract or a FAIL."""
    rel = WRAPPERS.get(tool)
    if not rel:
        return {"tool": tool, "exit_code": -1, "status": "FAIL",
                "verified": False, "summary": {},
                "errors": [f"unknown wrapper tool: {tool} "
                           f"(valid: {', '.join(sorted(WRAPPERS))})"],
                "warnings": [], "raw_log": ""}
    wrapper = WRAPPERS_DIR / rel
    if not wrapper.exists():
        return {"tool": tool, "exit_code": -1, "status": "FAIL",
                "verified": False, "summary": {},
                "errors": [f"wrapper missing: {wrapper}"],
                "warnings": [], "raw_log": ""}

    cmd: list[str]
    if os.access(wrapper, os.X_OK):
        cmd = [str(wrapper)] + list(args or [])
    else:                       # upstream ships mode 0644 -> bash fallback
        cmd = ["/usr/bin/env", "bash", str(wrapper)] + list(args or [])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"tool": tool, "exit_code": -1, "status": "FAIL",
                "verified": False, "summary": {},
                "errors": [f"wrapper timed out after {timeout}s"],
                "warnings": [], "raw_log": ""}
    except OSError as e:
        return {"tool": tool, "exit_code": -1, "status": "FAIL",
                "verified": False, "summary": {},
                "errors": [f"failed to launch wrapper: {e}"],
                "warnings": [], "raw_log": ""}

    stdout = proc.stdout.strip()
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return {"tool": tool, "exit_code": proc.returncode, "status": "FAIL",
                "verified": False, "summary": {},
                "errors": ["wrapper output was not valid JSON"],
                "warnings": [], "raw_log": "",
                "raw_output_excerpt": stdout[:500] or
                (proc.stderr.strip()[-500:] if proc.stderr else "")}
    if not (isinstance(result, dict) and result.get("status") in VALID_STATUSES):
        return {"tool": tool, "exit_code": proc.returncode, "status": "FAIL",
                "verified": False, "summary": {},
                "errors": ["wrapper JSON has no valid 'status' "
                           "(expected PASS, WARN or FAIL)"],
                "warnings": [], "raw_log": "",
                "raw_output_excerpt": stdout[:500]}
    return result
