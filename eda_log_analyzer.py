"""Iterative EDA log analyzer: vendor EDA tools (Synopsys/Cadence/Siemens) + LSF.

Parses logs produced by EDA tools into structured issues, classifies the
failure (failure_taxonomy), derives a retry strategy, and recommends the
next agent recipe — closing the observe→refine loop.

Supported log kinds (auto-detected):
  vcs_compile : Error-[Code] file, line "token" + explanation
  vcs_uvm_sim : UVM_ERROR/FATAL/@time/[id], report summary, TEST verdict,
                SVA assertion failures, timeout, licence checkout
  verdi       : *Error* / *Warning* + "Total N error(s), M warning(s)"
  lsf         : TERM_MEMLIMIT / TERM_RUNLIMIT / exit codes
  xcelium     : *E,SEVFX (file, line|col): msg; "Errors: N, Warnings: N"
  questa      : "# ** Error/Fatal/Warning:" + "Errors: N, Warnings: N"
  genus       : *Error,MSGID (file, LINE): msg (Cadence RC family)
  innovus     : **ERROR: / **WARNING: (Cadence physical design)
  calibre     : ERROR: / WARNING: + "Total Results:" (Siemens DRC/LVS)
"""
from __future__ import annotations

import re
from pathlib import Path

from .failure_taxonomy import classify_failure, retry_strategy_for

# ---------------------------------------------------------------- detection
def detect_kind(text: str) -> str:
    # vendor-specific markers first; the generic bare-"Error:" fallback must
    # stay last so Questa/Calibre/Innovus are not misrouted to vcs_compile
    if re.search(r"^\s*\*E,\w{5}|xmvlog|xrun:|\*\*\* xcelium", text, re.M):
        return "xcelium"
    if re.search(r"(?:^|\n)#\s*\*\*\s*(?:Error|Fatal|Warning):|vsim\b|\*\*\* Welcome to Questa", text):
        return "questa"
    if re.search(r"^\s*\*Error,\w+|\*\*\* Welcome to genus|genus>", text, re.M):
        return "genus"
    if re.search(r"\*\*ERROR:|\*\*WARNING:|\*\*\* Welcome to Innovus", text):
        return "innovus"
    if re.search(r"(?:^|\n)\s*(?:ERROR|WARNING):|\*\*CALIBRE|Total Results:", text, re.M):
        return "calibre"
    if re.search(r"Error-\[|Warning-\[", text):
        return "vcs_compile"
    if re.search(r"UVM_(INFO|WARNING|ERROR|FATAL)|UVM Report Summary|UVM_TESTNAME", text):
        return "vcs_uvm_sim"
    if re.search(r"(?:^|\n)\s*(?:\*\*)?\s*Error:", text):
        return "vcs_compile"   # bare tool errors (licence, file open, ...)
    if re.search(r"TERM_MEMLIMIT|TERM_RUNLIMIT|Successfully completed|Exited with exit code", text):
        return "lsf"
    # verdi last: "Total N error(s)" is too generic to win over VCS formats
    if re.search(r"\*Error\*|\*Warning\*|Total\s+\d+ error\(s\)", text):
        return "verdi"
    return "unknown"


# ---------------------------------------------------------------- parsers
def _parse_vcs_compile(text: str) -> dict:
    issues = []
    # VCS format (two lines):
    #   Error-[Code] Short description
    #   ./file.sv, 42 "token"
    for m in re.finditer(
            r'(?:^|\n)\s*(?:%\s*)?Error-\[([\w-]+)\][^\n]*\n\s*([^\n,]+),\s*(\d+)\s*(?:"([^"]*)")?'
            r'|(?:^|\n)\s*(?:%\s*)?Error-\[([\w-]+)\]\s+([^\n,]+),\s*(\d+)\s*(?:"([^"]*)")?',
            text):
        if m.group(1):  # two-line form
            code, f, ln, tok = m.group(1), m.group(2), m.group(3), m.group(4)
        else:            # same-line form
            code, f, ln, tok = m.group(5), m.group(6), m.group(7), m.group(8)
        issues.append({"severity": "ERROR", "category": f"vcs_{code.lower()}",
                       "source": f"{f.strip()}:{ln}",
                       "message": (tok or "").strip() or f"VCS {code} error"})
    # bare compile errors: "Error: message" / "** Error: ..."
    for m in re.finditer(r'(?:^|\n)\s*(?:\*\*)?\s*Error:\s*(.+)', text):
        msg = m.group(1).strip()
        if not any(msg in i["message"] or i["message"] in msg for i in issues):
            cat = "license" if re.search(r"licen[cs]e", msg, re.I) else "compile_error"
            issues.append({"severity": "ERROR", "category": cat,
                           "source": "", "message": msg})
    n_warn = len(re.findall(r"Warning-\[", text))
    return {"issues": issues, "counts": {"errors": len(issues), "warnings": n_warn}}


def _parse_vcs_uvm(text: str) -> dict:
    issues = []
    # UVM_ERROR/FATAL/WARNING @ time: reporter [id] message
    for m in re.finditer(
            r'UVM_(FATAL|ERROR|WARNING)\s+@\s+([\d.]+\s*\w*)\s*:\s*(\S+)\s+\[([^\]]+)\]\s*([^\n]*)',
            text):
        issues.append({"severity": f"UVM_{m.group(1)}", "category": "uvm",
                       "source": m.group(4), "message": m.group(5).strip(),
                       "time": m.group(2)})
    # SVA assertion failures (VCS style)
    for m in re.finditer(
            r'(?:%\s*Error-ASRT:|\*\*\s*Error:)?\s*([^\s:]+\.sv?[a-z]*)[:,]\s*\d+:\s*'
            # NB: compiled with re.X — literal spaces are ignored there, so
            # the separator between "assertion" and "failed" MUST be \s+
            r'(?:.*?)?[Aa]ssertion\s+failed\s*:?\s*(\w+)', text, re.X):
        # capture the line number too: source must be file:line, not just file
        line_m = re.search(r'[:,]\s*(\d+):', m.group(0))
        src = m.group(1) + (f":{line_m.group(1)}" if line_m else "")
        issues.append({"severity": "ERROR", "category": "sva_assertion",
                       "source": src, "message": f"assertion failed: {m.group(2)}"})
    if not any(i["category"] == "sva_assertion" for i in issues):
        for m in re.finditer(r'[Aa]ssertion failed\s*:?\s*(\w+)', text):
            issues.append({"severity": "ERROR", "category": "sva_assertion",
                           "source": "", "message": f"assertion failed: {m.group(1)}"})
    # UVM report summary counts
    counts = {}
    for sev in ("INFO", "WARNING", "ERROR", "FATAL"):
        m = re.search(rf'UVM_{sev}\s*:\s*(\d+)', text)
        if m:
            counts[sev.lower()] = int(m.group(1))
    # special patterns
    if re.search(r"Global timeout|PH_TIMEOUT|UVM_PH_TIMEOUT", text, re.I):
        issues.append({"severity": "FATAL", "category": "timeout",
                       "source": "phase", "message": "simulation timeout (objection never dropped?)"})
    if re.search(r"licen[cs]e.*(checkout|denied|unavailable)|Unable to checkout", text, re.I):
        issues.append({"severity": "FATAL", "category": "license",
                       "source": "", "message": "EDA licence checkout failed"})
    return {"issues": issues,
            "counts": counts or {"errors": sum(1 for i in issues if "ERROR" in i["severity"]),
                                 "warnings": sum(1 for i in issues if i["severity"] == "UVM_WARNING")}}


def _parse_verdi(text: str) -> dict:
    issues = []
    for m in re.finditer(r'\*(Error|Warning)\*\s*([^\n]+)', text):
        issues.append({"severity": m.group(1).upper(), "category": "verdi",
                       "source": "", "message": m.group(2).strip()})
    counts = {}
    m = re.search(r'Total\s+(\d+)\s+error\(s\),\s*(\d+)\s+warning\(s\)', text)
    if m:
        counts = {"errors": int(m.group(1)), "warnings": int(m.group(2))}
    return {"issues": issues, "counts": counts}


def _parse_lsf(text: str) -> dict:
    issues = []
    if "TERM_MEMLIMIT" in text:
        issues.append({"severity": "FATAL", "category": "resource_memlimit",
                       "source": "lsf", "message": "job killed by MEMLIMIT"})
    if "TERM_RUNLIMIT" in text:
        issues.append({"severity": "FATAL", "category": "resource_runlimit",
                       "source": "lsf", "message": "job killed by RUNLIMIT"})
    m = re.search(r'Exited with exit code (\d+)', text)
    if m and int(m.group(1)) != 0:
        issues.append({"severity": "ERROR", "category": "exit_code",
                       "source": "lsf", "message": f"exit code {m.group(1)}"})
    if "Successfully completed" in text:
        return {"issues": [], "counts": {"errors": 0, "warnings": 0}}
    return {"issues": issues,
            "counts": {"errors": len(issues), "warnings": 0}}


PARSERS = {"vcs_compile": _parse_vcs_compile, "vcs_uvm_sim": _parse_vcs_uvm,
           "verdi": _parse_verdi, "lsf": _parse_lsf}


def _cadence_errors_warnings_summary(text: str) -> dict:
    counts = {}
    m = re.search(r'Errors:\s*(\d+),\s*Warnings:\s*(\d+)', text)
    if m:
        counts = {"errors": int(m.group(1)), "warnings": int(m.group(2))}
    return counts


def _parse_xcelium(text: str) -> dict:
    """Xcelium/xrun: *E,SEVFX (file, line|col): message."""
    issues = []
    for m in re.finditer(r'\*([EWFC]),(\w+)\s*\(([^,()]+),\s*([^)]+)\):\s*([^\n]+)', text):
        sev = {"E": "ERROR", "W": "WARNING", "F": "FATAL", "C": "FATAL"}[m.group(1)]
        issues.append({"severity": sev, "category": f"xcelium_{m.group(2).lower()}",
                       "source": f"{m.group(3).strip()}:{m.group(4).strip()}",
                       "message": m.group(5).strip()})
    counts = _cadence_errors_warnings_summary(text)
    if not counts:
        counts = {"errors": sum(1 for i in issues if i["severity"] == "ERROR"),
                  "warnings": sum(1 for i in issues if i["severity"] == "WARNING")}
    return {"issues": issues, "counts": counts}


def _parse_questa(text: str) -> dict:
    """Questa/vsim: '# ** Error: msg', '# ** Fatal: msg', 'Errors: N, Warnings: N'."""
    issues = []
    for m in re.finditer(r'(?:^|\n)#?\s*\*\*\s*(Error|Fatal|Warning):\s*([^\n]+)', text):
        sev = {"Error": "ERROR", "Fatal": "FATAL", "Warning": "WARNING"}[m.group(1)]
        msg = m.group(2).strip()
        cat = "license" if re.search(r"licen[cs]e", msg, re.I) else "questa"
        issues.append({"severity": sev, "category": cat,
                       "source": "", "message": msg})
    for m in re.finditer(r'([^\s:]+\.sv?[a-z]*)(?:\((\d+)\))?', text):
        if any(i["source"] == "" and m.group(1) in i["message"] for i in issues):
            i = next(i for i in issues if i["source"] == "" and m.group(1) in i["message"])
            i["source"] = m.group(1) + (f":{m.group(2)}" if m.group(2) else "")
    counts = _cadence_errors_warnings_summary(text)
    if not counts:
        counts = {"errors": sum(1 for i in issues if i["severity"] in ("ERROR", "FATAL")),
                  "warnings": sum(1 for i in issues if i["severity"] == "WARNING")}
    return {"issues": issues, "counts": counts}


def _parse_genus(text: str) -> dict:
    """Genus (Cadence RC family): *Error,MSGID (file, LINE): message."""
    issues = []
    for m in re.finditer(r'\*(Error|Warning),(\w+)\s*\(([^,()]+),\s*([^)]+)\):\s*([^\n]+)', text):
        sev = m.group(1).upper()
        issues.append({"severity": sev, "category": f"genus_{m.group(2).lower()}",
                       "source": f"{m.group(3).strip()}:{m.group(4).strip()}",
                       "message": m.group(5).strip()})
    counts = {"errors": sum(1 for i in issues if i["severity"] == "ERROR"),
              "warnings": sum(1 for i in issues if i["severity"] == "WARNING")}
    return {"issues": issues, "counts": counts}


def _parse_innovus(text: str) -> dict:
    """Innovus: '**ERROR: msg' / '**WARNING: msg'."""
    issues = []
    for m in re.finditer(r'\*\*(ERROR|WARNING):\s*([^\n]+)', text):
        issues.append({"severity": m.group(1).capitalize() if m.group(1) == "WARNING" else "ERROR",
                       "category": "innovus", "source": "",
                       "message": m.group(2).strip()})
    counts = {"errors": sum(1 for i in issues if i["severity"] == "ERROR"),
              "warnings": sum(1 for i in issues if i["severity"] == "WARNING")}
    return {"issues": issues, "counts": counts}


def _parse_calibre(text: str) -> dict:
    """Calibre DRC/LVS: 'ERROR: msg', 'WARNING: msg', 'Total Results: N'."""
    issues = []
    for m in re.finditer(r'(?:^|\n)\s*(ERROR|WARNING):\s*([^\n]+)', text):
        issues.append({"severity": m.group(1).capitalize() if m.group(1) == "WARNING" else "ERROR",
                       "category": "calibre", "source": "",
                       "message": m.group(2).strip()})
    counts = {"errors": sum(1 for i in issues if i["severity"] == "ERROR"),
              "warnings": sum(1 for i in issues if i["severity"] == "WARNING")}
    m = re.search(r'Total Results:\s*(\d+)', text)
    if m and int(m.group(1)) > 0 and not issues:
        issues.append({"severity": "ERROR", "category": "calibre_results",
                       "source": "", "message": f"{m.group(1)} DRC/LVS result(s)"})
        counts["errors"] += int(m.group(1))
    return {"issues": issues, "counts": counts}


PARSERS.update({"xcelium": _parse_xcelium, "questa": _parse_questa,
                "genus": _parse_genus, "innovus": _parse_innovus,
                "calibre": _parse_calibre})


# ---------------------------------------------------------------- recommendation
RECIPE_BY_CATEGORY = {
    "sva_assertion": "assertion_failure_triage",
    "uvm": "uvm_verification_flow",
    "timeout": "uvm_verification_flow",
    "compile_error": "uvm_verification_flow",
    "license": "simulation_run",
    "resource_memlimit": "simulation_run",
    "resource_runlimit": "simulation_run",
    "exit_code": "simulation_run",
    "verdi": "simulation_run",
    "xcelium_timeout": "simulation_run",
    "questa": "uvm_verification_flow",
    "license": "simulation_run",
    "genus": "logic_synthesis_flow",
    "innovus": "physical_design_flow",
    "calibre": "signoff_tapeout",
    "calibre_results": "signoff_tapeout",
}


def _recommend(parsed: dict, kind: str) -> dict:
    cats = {i["category"] for i in parsed["issues"]}
    if not cats:
        return {"recipe": None, "retry_strategy": "none",
                "next_step": "proceed", "note": "no failures detected in log"}
    for cat, recipe in RECIPE_BY_CATEGORY.items():
        if cat in cats:
            return {"recipe": recipe, "trigger_category": cat,
                    "next_step": f"run recipe: {recipe}"}
    # domain default by tool kind when category is tool-specific but unmapped
    kind_default = {"genus": "logic_synthesis_flow",
                    "innovus": "physical_design_flow",
                    "calibre": "signoff_tapeout",
                    "xcelium": "simulation_run",
                    "questa": "uvm_verification_flow",
                    "vcs_uvm_sim": "uvm_verification_flow",
                    "vcs_compile": "uvm_verification_flow",
                    "verdi": "simulation_run"}.get(kind, "uvm_verification_flow")
    if kind_default != "uvm_verification_flow":
        return {"recipe": kind_default, "trigger_category": sorted(cats)[0],
                "next_step": f"run recipe: {kind_default}"}
    return {"recipe": "uvm_verification_flow", "trigger_category": sorted(cats)[0],
            "next_step": "run recipe: uvm_verification_flow"}


def analyze_log(path: str, kind: str | None = None) -> dict:
    """Analyze one EDA log file; returns verdict/issues/classification/next actions."""
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"log not found: {path}"}
    text = p.read_text(errors="ignore")
    return analyze_text(text, kind=kind, source=str(p))


def analyze_text(text: str, kind: str | None = None, source: str = "<text>") -> dict:
    kind = kind or detect_kind(text)
    if kind not in PARSERS:
        return {"ok": True, "kind": "unknown", "verdict": "UNKNOWN",
                "issues": [], "counts": {}, "note": "unrecognized log format",
                "source": source}
    parsed = PARSERS[kind](text)
    counts = parsed["counts"]
    n_err = counts.get("errors", 0) or sum(1 for i in parsed["issues"]
                                           if "ERROR" in i["severity"] or i["severity"] == "FATAL")
    n_fatal = sum(1 for i in parsed["issues"] if i["severity"] == "FATAL")
    if "** TEST PASSED **" in text and n_err == 0:
        verdict = "PASS"
    elif "** TEST FAILED **" in text or n_err > 0:
        verdict = "FAIL"
    elif counts.get("warnings", 0):
        verdict = "WARN"
    elif "Successfully completed" in text:
        verdict = "PASS"
    else:
        verdict = "UNKNOWN"
    # classify from the most informative messages
    # include severity: hints like "uvm_error"/"uvm_fatal" live in the
    # severity field, which was previously missing from the classify input
    cls = classify_failure(" ".join(
        f"{i['severity']}: {i['message']}" for i in parsed["issues"])
        or text[:500])
    if verdict == "PASS":
        cls = "none"
    rec = _recommend(parsed, kind)
    return {
        "ok": True, "source": source, "kind": kind, "verdict": verdict,
        "issues": parsed["issues"][:50], "counts": {**counts, "issue_count": len(parsed["issues"])},
        "failure_class": cls,
        "retry_strategy": retry_strategy_for(cls),
        "recommended": rec,
    }


# ------------------------------------------------- manual step lookup (UG)
_UG_QUERY_BY_KIND: dict[str, str] = {
    "vcs_compile": "VCS compilation elaboration",
    "vcs_uvm_sim": "VCS UVM simulation run",
    "verdi": "Verdi waveform debug",
    "xcelium": "Xcelium simulation run",
    "questa": "Questa simulation run",
    "genus": "Genus synthesis flow",
    "innovus": "Innovus physical design flow",
    "calibre": "Calibre rule deck run",
    "lsf": "job submission resource limits",
}

_UG_QUERY_BY_CLASS: dict[str, str] = {
    "timing": "timing constraints setup hold",
    "functional": "simulation testbench debug",
    "power_area": "power area optimization",
    "coverage_gap": "coverage flow",
    "connectivity": "connectivity netlist check",
    "drc_lvs": "DRC LVS rule deck",
    "tool_error": "license checkout environment",
    "resource_limit": "memory limit job resources",
    "spec_gap": "verification plan requirements",
}


def ug_step_queries(kind: str | None, failure_class: str | None) -> list[str]:
    """Generate 1-2 UG manual queries for a failed (kind, failure_class) pair."""
    queries: list[str] = []
    base = _UG_QUERY_BY_KIND.get(kind or "")
    if base:
        queries.append(base)
    extra = _UG_QUERY_BY_CLASS.get(failure_class or "")
    if extra and extra not in queries:
        queries.append(extra)
    return queries[:2]


_DVCON_QUERY_BY_CLASS: dict[str, str] = {
    "timing": "SDC coverage closure timing constraints",
    "functional": "assertion quality formal verification debug",
    "power_area": "low-power verification PPA optimization",
    "coverage_gap": "coverage closure stimulus generation",
    "connectivity": "equivalence checking ECO netlist",
    "drc_lvs": "sign-off physical verification flow",
    "tool_error": "regression infrastructure job management",
    "resource_limit": "regression management scheduling",
    "spec_gap": "specification matching verification planning",
}


def dvcon_queries(kind: str | None, failure_class: str | None) -> list[str]:
    """Generate 1-2 DVCon paper-corpus queries for a failed run."""
    queries: list[str] = []
    class_q = _DVCON_QUERY_BY_CLASS.get(failure_class or "")
    if class_q:
        queries.append(class_q)
    if kind == "uvm":
        queries.append("UVM testbench LLM verification IP")
    elif kind == "coverage":
        queries.append("coverage closure machine learning")
    return queries[:2]
