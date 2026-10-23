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
    log_text = ""
    try:
        log_text = Path(path).read_text(errors="ignore")
    except OSError:
        pass
    res = analyze_log(path, kind=args.get("kind"))
    # Failed runs: attach step-level UG manual guidance when the vector
    # corpora are available (unified RAG fan-out: UG steps + merged manual
    # corpus in parallel). Degrade gracefully when none is built.
    if res.get("ok") and res.get("verdict") != "PASS" and res.get("failure_class"):
        try:
            from . import rag_router
            queries = ug_step_queries(res.get("kind"), res.get("failure_class"))
            manual = []
            for q in queries:
                sr = rag_router.search(q, sources=["ug", "manual"],
                                       kind="steps", top_k=3, timeout=5.0)
                hits = [h for r in sr.get("results", []) for h in r.get("hits", [])]
                if hits:
                    manual.append({"query": q, "hits": hits})
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
        # PCIe-domain guidance: when the failing log is PCIe-related, attach
        # chapter/step-level manual guidance from the in-repo PCIe OVM guide.
        _PCIE_HINTS = ("pcie", "ovm", "svt_pcie", "ltssm", "dllp", "tlp",
                       "link train", "root complex", "endpoint")
        low = log_text.lower()
        if any(h in low for h in _PCIE_HINTS):
            try:
                from . import pcie_index
                if pcie_index._load() is not None:
                    steps = []
                    for q in ug_step_queries(res.get("kind"),
                                             res.get("failure_class")):
                        sr = pcie_index.search(q, top_k=3, kind="steps")
                        if sr.get("hits"):
                            steps.append({"query": q, "hits": sr["hits"]})
                    if steps:
                        res["pcie_manual_steps"] = steps
            except Exception as exc:  # noqa: BLE001
                res.setdefault("notes", []).append(
                    f"pcie manual lookup skipped: {exc}")
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


def pcie_search(args: dict) -> dict:
    """PCIe OVM User Guide retrieval (chapter/steps/code/prose chunks)."""
    from . import pcie_index
    return pcie_index.search(
        args.get("query", ""),
        top_k=max(1, min(20, int(args.get("top_k") or 5))),
        kind=args.get("kind"),
    )


def manual_search(args: dict) -> dict:
    """Technical-manual corpus retrieval (chapter/section/steps/flow/example/prose)."""
    from . import manual_ingest
    return manual_ingest.search(
        args.get("query", ""),
        product=args.get("product"),
        doc=args.get("doc"),
        kind=args.get("kind"),
        top_k=max(1, min(20, int(args.get("top_k") or 5))),
    )


def manual_ingest_op(args: dict) -> dict:
    """Build/status for the technical-manual corpus pipeline."""
    from . import manual_ingest
    root = args.get("root")
    out = args.get("out")
    op = args.get("op", "status")
    if op == "build":
        return manual_ingest.build(root, out)
    if op == "scan":
        return manual_ingest.scan(root)
    if op == "sft":
        return manual_ingest.generate_sft(out)
    return manual_ingest.status(out)


def rag_search(args: dict) -> dict:
    """Unified cross-corpus RAG retrieval (parallel fan-out)."""
    from . import rag_router
    sources = args.get("sources")
    return rag_router.search(
        args.get("query", ""),
        sources=sources if isinstance(sources, list) else None,
        top_k=max(1, min(10, int(args.get("top_k") or 4))),
        timeout=max(1.0, min(30.0, float(args.get("timeout") or 5.0))),
        product=args.get("product"),
        kind=args.get("kind"),
        category=args.get("category"),
    )

def uvm_methodology_op(args: dict) -> dict:
    """UVM 1.2 methodology decision layer (patterns / phase map / checklist)."""
    from . import uvm_methodology as um
    op = args.get("op", "decide")
    if op == "decide":
        return um.decide(args.get("query", ""))
    if op == "pattern":
        return um.get_pattern(args.get("pattern", ""))
    if op == "phase_map":
        return um.get_phase_map()
    if op == "checklist":
        return um.get_checklist(args.get("level", "block_level"))
    if op == "pitfalls":
        return {"pitfalls": um.get_all_pitfalls()}
    if op == "patterns":
        return {"available": um.list_patterns()}
    if op == "full":
        q = args.get("query", "")
        return um.methodology_checklist_for_intent(q)
    return {"error": f"unknown op: {op} (decide|pattern|phase_map|checklist|pitfalls|patterns|full)"}


def rag_search_op(args: dict) -> dict:
    """Unified RAG search: routes to the right index backends and fuses results."""
    from . import rag_router
    return rag_router.rag_search(
        args.get("query", ""),
        top_k=max(1, min(20, int(args.get("top_k") or 5))),
        backends=args.get("backends"),
        kind=args.get("kind"),
        product=args.get("product"),
    )


def rag_status_op(args: dict) -> dict:
    """Health check for all RAG backends."""
    from . import rag_router
    return rag_router.status()



def scheduler_status_op(args: dict) -> dict:
    """Scheduler health: cache stats, circuit breaker state, warm threads."""
    from . import scheduler
    return scheduler.scheduler_status()


def scheduler_preload_op(args: dict) -> dict:
    """Preload heavy indexes into memory for faster first query."""
    from . import scheduler
    return scheduler.preload_indexes(background=args.get("background", True))


def scheduler_cache_clear_op(args: dict) -> dict:
    """Clear the scheduler result cache."""
    from . import scheduler
    n = scheduler.cache_clear()
    return {"cleared": n}



def post_rtl_methodology_op(args: dict) -> dict:
    """Post-RTL verification methodology decision layer (7-stage sign-off)."""
    from . import post_rtl_methodology as prm
    op = args.get("op", "decide")
    if op == "decide":
        return prm.decide(args.get("query", ""))
    if op == "stage":
        return prm.get_stage(args.get("stage", ""))
    if op == "workflow":
        return prm.get_full_workflow()
    if op == "convergence":
        return prm.convergence_status(args.get("measurements", {}))
    if op == "pitfalls":
        return {"pitfalls": prm.get_pitfalls(args.get("stage"))}
    if op == "stages":
        return {"available": prm.list_stages()}
    if op == "tool_chain":
        return {"tools": prm.get_tool_chain(args.get("stage", ""))}
    if op == "full":
        return prm.post_rtl_checklist_for_intent(args.get("query", ""))
    return {"error": f"unknown op: {op}"}



def eda_route_op(args: dict) -> dict:
    """EDA tool routing: intent → tool → command template validation."""
    from . import eda_tool_router as etr
    op = args.get("op", "match")
    if op == "match":
        return etr.match_tool_route(args.get("query", ""))
    if op == "validate":
        return etr.validate_command(args.get("tool", ""), args.get("command", []))
    if op == "availability":
        return etr.check_availability(args.get("tool", ""))
    if op == "routes":
        return {"routes": etr.get_all_routes()}
    if op == "pitfalls":
        return {"pitfalls": etr.get_pitfalls(args.get("tool"))}
    return {"error": f"unknown op: {op}"}



def dv_tb_generate_op(args: dict) -> dict:
    """Intelligent UVM TB generation from methodology patterns."""
    from . import dv_infrastructure as dvi
    return dvi.generate_uvm_tb(
        name=args.get("name", "fifo"),
        interface_type=args.get("interface_type", "generic"),
        data_width=args.get("data_width", 8),
        components=args.get("components"),
        output_dir=args.get("output_dir"),
    )


def dv_test_plan_op(args: dict) -> dict:
    """Create dependency-aware test plan with seeds."""
    from . import dv_infrastructure as dvi
    return dvi.create_test_plan(
        tests=args.get("tests", []),
        simulator=args.get("simulator", "vcs"),
        seeds=args.get("seeds"),
        max_parallel=args.get("max_parallel", 4),
    )


def dv_coverage_op(args: dict) -> dict:
    """Parse coverage log + create closure plan."""
    from . import dv_infrastructure as dvi
    cov = dvi.parse_coverage_log(args.get("log_content", ""))
    if args.get("target_pct"):
        plan = dvi.create_coverage_plan(cov, args["target_pct"])
        cov["closure_plan"] = plan
    return cov


def dv_sim_config_op(args: dict) -> dict:
    """Get optimized simulator configuration (DPO/ICO/RDA)."""
    from . import dv_infrastructure as dvi
    if args.get("op") == "compare":
        return {"configs": dvi.compare_sim_configs()}
    return dvi.get_sim_config(
        args.get("config_name", "baseline"),
        extra_compile=args.get("extra_compile"),
        extra_sim=args.get("extra_sim"),
    )


LOCAL_TOOLS = {
    "generate_testbench": generate_testbench,
    "check_uvm_compliance": check_uvm_compliance,
    "check_eda_tools": check_eda_tools,
    "run_simulation": run_sim,
    "open_waveform": open_waveform,
    "analyze_eda_log": analyze_eda_log,
    "pcie_search": pcie_search,
    "manual_search": manual_search,
    "manual_ingest_op": manual_ingest_op,
    "rag_search": rag_search,
    "uvm_methodology_op": uvm_methodology_op,
    "rag_search_op": rag_search_op,
    "rag_status_op": rag_status_op,
    "scheduler_status_op": scheduler_status_op,
    "scheduler_preload_op": scheduler_preload_op,
    "scheduler_cache_clear_op": scheduler_cache_clear_op,
    "post_rtl_methodology_op": post_rtl_methodology_op,
    "eda_route_op": eda_route_op,
    "dv_tb_generate_op": dv_tb_generate_op,
    "dv_test_plan_op": dv_test_plan_op,
    "dv_coverage_op": dv_coverage_op,
    "dv_sim_config_op": dv_sim_config_op,
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
