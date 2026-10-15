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

from .eda_log_analyzer import analyze_log
from .eda_tools import discover, open_verdi, run_simulation
from .eda_wrappers import list_wrappers, run_wrapper
from .design_state import DesignState, DEFAULT_STATE_PATH
from .digital_memory import DomainMemory, VALID_DOMAINS, qor_trends
from .flow_guide import overview, phase_detail, route_intent
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

TEMPLATE_ROOT = Path("/tools/lsf_api/uvm_tb")
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
    """Run a UVM simulation with VCS on the given project root."""
    root = args.get("root") or str(TEMPLATE_ROOT)
    return run_simulation(root, testname=args.get("testname", "fifo_smoke_test"))


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
    return analyze_log(path, kind=args.get("kind"))


def list_eda_wrappers(args: dict) -> dict:
    """Enumerate the vendored output-filtering EDA wrappers."""
    items = list_wrappers()
    return {"ok": True, "wrappers": items,
            "available": [w["tool"] for w in items if w["exists"]]}


def run_eda_wrapper(args: dict) -> dict:
    """Run one vendored wrapper (compact JSON; exit 0 is never a pass)."""
    tool = args.get("tool", "")
    tool_args = args.get("args") or []
    if isinstance(tool_args, str):
        tool_args = [tool_args]
    return run_wrapper(tool, tool_args, timeout=int(args.get("timeout", 300)))


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
    return {"ok": False, "error": f"unknown op: {op} (overview|phase|route)"}


LOCAL_TOOLS = {
    "generate_testbench": generate_testbench,
    "check_uvm_compliance": check_uvm_compliance,
    "check_eda_tools": check_eda_tools,
    "run_simulation": run_sim,
    "open_waveform": open_waveform,
    "analyze_eda_log": analyze_eda_log,
    "list_eda_wrappers": list_eda_wrappers,
    "run_eda_wrapper": run_eda_wrapper,
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
