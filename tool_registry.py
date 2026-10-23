"""Tool    ToolDef(
        name="chip_dv_infrastructure",
        description="DV 验证基础设施: op=generate_tb(UVM TB 自动生成)/test_plan(测试调度)/coverage(覆盖率收集分析)/sim_config(仿真器配置优化 DPO/ICO/RDA)",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["generate_tb", "test_plan",
                                               "coverage", "sim_config", "compare"]},
                               "name": {"type": "string"},
                               "interface_type": {"type": "string",
                                                   "enum": ["apb", "axi4", "fifo", "generic"]},
                               "data_width": {"type": "integer"},
                               "tests": {"type": "array"},
                               "seeds": {"type": "array"},
                               "log_content": {"type": "string"},
                               "target_pct": {"type": "number"},
                               "config_name": {"type": "string"},
                               "max_parallel": {"type": "integer"}},
                "required": ["op"]},
        handler=_dv_infra_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
 registry — single source of truth for the MCP tool surface.

Split out of mcp_tools.py (Step 6): every ToolDef, handler and the
_TOOL_DOMAINS client-filter map live here; mcp_tools keeps the server
plumbing (dispatch, error contract, audit) and re-exports this module's
names for backward compatibility.
"""

from __future__ import annotations

import queue as _queue_mod
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .local_tools import call_local
from . import metrics
from .agent import AUTO_DISTILL_MIN_RECORDS
from .domain_flows import DOMAIN_FLOWS


# Step 19: single source for every tool-level `domain` argument.
# Client-filter namespaces (_TOOL_DOMAINS values) are capability domains;
# this enum is the engineering-flow domain space and MUST stay equal to
# DOMAIN_FLOWS / qor_trends.VALID_DOMAINS / distill VALID_DOMAINS.
DOMAIN_ENUM = sorted(DOMAIN_FLOWS)


def get_agent():
    # lazy: avoid a circular import — the agent singleton and its
    # environment/paths live in mcp_tools
    from .mcp_tools import get_agent as _get_agent
    return _get_agent()


# ---------------------------------------------------------------------------
# ToolDef + TOOL_DEFS (20 tools)
# ---------------------------------------------------------------------------

_FALSE = lambda r: False  # noqa: E731
_NOT_OK = lambda r: not r.get("ok", False)  # noqa: E731

# annotation hints: all tools are non-destructive (nothing deletes user data);
# read-only tools are additionally marked so clients may call them in parallel.
_AN_RO = dict(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
_AN_MUT = dict(read_only_hint=False, destructive_hint=False, idempotent_hint=False)


@dataclass
class ToolDef:
    name: str
    description: str
    schema: dict                     # JSON schema (legacy inputSchema / code-gen source)
    handler: Callable[..., Any]      # (args: dict, [progress_cb]) -> domain result
    is_error: Callable[[Any], bool] = _FALSE
    render: Callable[[Any], str] | None = None   # default: compact JSON
    annotations: dict = field(default_factory=lambda: dict(_AN_MUT))
    timeout: float | None = None     # server-side cap (seconds); subprocess ops cap themselves first
    progress: bool = False           # coarse start/done progress via MCP ctx
    step_progress: bool = False      # fine-grained per-step progress (chip_agent_run)
    domain: str = "general"          # client-side filter tag


def _run_report_is_error(rep) -> bool:
    return any(not s.ok for s in rep.steps) or not rep.steps


def _run_handler(args: dict, progress_cb=None):
    """chip_agent_run: everything except `intent` is the run context."""
    ctx = {k: v for k, v in args.items() if k != "intent"} or None
    return get_agent().run(args["intent"], context=ctx, progress_cb=progress_cb)


def _history_handler(args: dict):
    ag = get_agent()
    if not ag.store:
        raise tool_error("config_missing", "CHIP_AGENT_DB not set")
    return {"history": ag.store.history()}


def _recall_handler(args: dict) -> dict:
    """chip_agent_recall: proactive memory recall BEFORE starting work.

    One read-only call surfaces everything the agent remembers about an
    intent: past experience (recency/env-weighted), the mapped domain's
    distilled knowledge, the domain's own experience records, the effective
    (proven-successful) skill chains learned by the agent, and per-skill
    recurring failure classes with the strategies that fixed them.
    """
    intent = args["intent"]
    limit = max(1, min(20, int(args.get("limit") or 5)))
    ag = get_agent()
    out: dict = {"intent": intent}
    domain = args.get("domain")
    if not domain:
        try:                       # domain guess via the same mapping plan() uses
            domain = ag.plan(intent).get("domain")
        except Exception:
            domain = None
    if domain:
        out["domain"] = domain
        try:
            from .digital_memory import DomainMemory
            mem = DomainMemory(domain)
            out["knowledge_preview"] = mem.knowledge()[:800]
            out["domain_records"] = mem.search(intent, limit=3)
            out["effective_variants"] = mem.plan_variants(limit=3)
            # proactive-learning hint: experiences outgrew distilled
            # knowledge -> nudge the caller (or scheduler) to distill
            jl, kd = mem.jsonl, mem.dir / "knowledge.md"
            if jl.exists() and kd.exists() and \
                    jl.stat().st_mtime > kd.stat().st_mtime and \
                    len(mem.records()) >= AUTO_DISTILL_MIN_RECORDS:
                out["distill_recommended"] = True
        except Exception as e:                 # memory is best-effort
            out["domain_memory_error"] = str(e)
    # proactive DVCon methodology memory: verification-related intents get a
    # distilled paper-trends preview (best-effort, never breaks recall)
    try:
        if domain == "verification" or any(
                w in intent.lower() for w in (
                    "verif", "uvm", "formal", "coverage", "regression",
                    "cdc", "sdc", "assert", "upf", "power", "isolation",
                    "retention")):
            from . import dvcon_index
            dg = dvcon_index._dvcon_root() / "dvcon_knowledge.md"
            if not dg.exists():
                dvcon_index.digest()
            text = dg.read_text(encoding="utf-8", errors="replace")
            # intent-track focused preview: extract the matching track section
            lo = intent.lower()
            if any(w in lo for w in ("power", "upf", "isolation", "retention")):
                track = "low-power"
            elif any(w in lo for w in ("cdc", "clock", "reset", "x-prop")):
                track = "cdc"
            elif any(w in lo for w in ("sdc", "timing", "constraint")):
                track = "timing"
            elif any(w in lo for w in ("llm", "agent", "generative", "ai ")):
                track = "ai"
            else:
                track = "verification"
            marker = f"## track: {track}"
            start = text.find(marker)
            if start >= 0:
                nxt = text.find("\n## track:", start + len(marker))
                section = text[start:nxt if nxt >= 0 else len(text)]
            else:
                section = text
            out["dvcon_trends_preview"] = section[:1200]
            out["dvcon_trends_track"] = track
    except Exception as e:
        out["dvcon_trends_error"] = str(e)
    if ag.experience:
        try:
            out["past_experience"] = ag.experience.search(
                intent, limit=limit, env_fp=ag._env())
        except Exception as e:
            out["experience_error"] = str(e)
    if ag.store:
        try:
            matrix = ag.store.skill_failure_strategies(min_samples=2)
            out["skill_risk_strategies"] = {
                sk: [{"failure_class": fc, "count": cnt, "strategy": strat}
                     for fc, cnt, strat in hits]
                for sk, hits in list(matrix.items())[:10]}
        except Exception as e:
            out["db_error"] = str(e)
    # UVM 1.2 methodology decision injection: when the intent mentions UVM
    # patterns, inject the matching methodology so the caller gets actionable
    # "how to build" guidance alongside the existing experience/memory data.
    lo = intent.lower()
    if any(w in lo for w in ("driver", "monitor", "agent", "scoreboard",
                             "sequence", "env", "uvm", "factory override",
                             "objection", "tlm", "register model", "phase")):
        try:
            from . import uvm_methodology as um
            full = um.methodology_checklist_for_intent(intent)
            if full.get("matched"):
                out["uvm_methodology"] = {
                    "best_pattern": full["best_pattern"],
                    "rationale": full["best_rationale"],
                    "phase_rules": {
                        k: v["actions"] for k, v in
                        full.get("pattern_data", {}).get("phases", {}).items()
                    } if isinstance(full.get("pattern_data", {}).get("phases"), dict) else {},
                    "pitfalls": full.get("pattern_data", {}).get("pitfalls", []),
                    "checklist_level": full.get("checklist_level"),
                    "checklist": full.get("checklist", []),
                }
        except Exception:
            pass  # methodology is a bonus, never block the recall
    return out


def _ug_search_handler(args: dict) -> dict:
    """chip_ug_search: VCS+Verdi UG vector retrieval (stdlib+numpy only)."""
    from . import ug_index
    return ug_index.search(
        args["query"],
        product=args.get("product"),
        top_k=max(1, min(20, int(args.get("top_k") or 5))),
        kind=args.get("kind"),
    )


def _dvcon_search_handler(args: dict) -> dict:
    """chip_dvcon_search: DVCon 2025/2026 paper corpus retrieval."""
    from . import dvcon_index
    query = args.get("query") or ""
    if not query and args.get("failure_class"):
        from .eda_log_analyzer import dvcon_queries
        qs = dvcon_queries(None, args["failure_class"])
        query = qs[0] if qs else args["failure_class"].replace("_", " ")
    if not query:
        return {"error": "query or failure_class is required"}
    return dvcon_index.search(
        query,
        year=args.get("year"),
        kind=args.get("kind"),
        tag=args.get("tag"),
        top_k=max(1, min(20, int(args.get("top_k") or 5))),
    )


def _npi_handler(args: dict) -> dict:
    """chip_npi: Synopsys NPI C API browsing/search (stdlib only)."""
    from . import npi_index
    op = args.get("op", "search")
    if op == "families":
        return npi_index.families()
    if op == "get":
        return npi_index.get(args["keyword"])
    return npi_index.search(
        args["keyword"], family=args.get("family"),
        top_k=max(1, min(100, int(args.get("top_k") or 20))),
    )


def _uvm_src_handler(fn: str, args: dict) -> dict:
    """Shared dispatcher for the chip_uvm_* source-knowledge tools."""
    from . import uvm_src_tools as u
    try:
        if fn == "search":
            text = u.search_source(
                args["pattern"],
                file_filter=args.get("file_filter", ""),
                case_sensitive=bool(args.get("case_sensitive", False)),
                context_lines=max(0, min(10, int(args.get("context_lines") or 3))),
                max_results=max(1, min(100, int(args.get("max_results") or 30))))
        elif fn == "class":
            text = u.get_class_definition(args["class_name"])
        elif fn == "hierarchy":
            text = u.get_class_hierarchy(
                args["class_name"], args.get("direction", "both"))
        elif fn == "methods":
            text = u.list_methods(args["class_name"])
        elif fn == "method_source":
            text = u.get_method_source(args["class_name"], args["method_name"])
        elif fn == "classes":
            text = u.list_all_classes(args.get("filter", ""))
        elif fn == "file":
            text = u.get_file_content(
                args["relative_path"],
                start_line=max(1, int(args.get("start_line") or 1)),
                end_line=max(0, int(args.get("end_line") or 0)))
        elif fn == "files":
            text = u.list_files(args.get("directory_filter", ""))
        elif fn == "macro":
            text = u.get_macro_definition(args["macro_name"])
        elif fn == "semantic":
            text = u.semantic_search(
                args["query"],
                top_k=max(1, min(12, int(args.get("top_k") or 6))),
                source_only=bool(args.get("source_only", False)))
        elif fn == "explain":
            text = u.explain_uvm_concept(args["concept"])
        else:
            return {"error": f"unknown uvm tool: {fn}"}
        return {"ok": True, "text": text[:16000]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _uvm_search_handler(args: dict) -> dict:
    return _uvm_src_handler("search", args)


def _uvm_class_handler(args: dict) -> dict:
    return _uvm_src_handler("class", args)


def _uvm_hierarchy_handler(args: dict) -> dict:
    return _uvm_src_handler("hierarchy", args)


def _uvm_methods_handler(args: dict) -> dict:
    return _uvm_src_handler("methods", args)


def _uvm_method_source_handler(args: dict) -> dict:
    return _uvm_src_handler("method_source", args)


def _uvm_classes_handler(args: dict) -> dict:
    return _uvm_src_handler("classes", args)


def _uvm_file_handler(args: dict) -> dict:
    return _uvm_src_handler("file", args)


def _uvm_files_handler(args: dict) -> dict:
    return _uvm_src_handler("files", args)


def _uvm_macro_handler(args: dict) -> dict:
    return _uvm_src_handler("macro", args)


def _uvm_semantic_handler(args: dict) -> dict:
    return _uvm_src_handler("semantic", args)


def _uvm_explain_handler(args: dict) -> dict:
    return _uvm_src_handler("explain", args)


def _uvm_notes_handler(args: dict) -> dict:
    """chip_uvm_notes: UVM 1.2 source code analysis notes search."""
    from . import uvm_src_tools
    return uvm_src_tools.search_notes(
        args["query"],
        top_k=max(1, min(20, int(args.get("top_k") or 5))),
        subsystem=args.get("subsystem"),
        kind=args.get("kind"),
    )




def _uvm_methodology_handler(args: dict) -> dict:
    """chip_uvm_methodology: UVM 1.2 methodology decision layer."""
    from .local_tools import call_local
    return call_local("uvm_methodology_op", args)




def _rag_search_handler(args: dict) -> dict:
    """chip_rag_search: unified RAG search across all index backends."""
    from .local_tools import call_local
    return call_local("rag_search_op", args)


def _rag_status_handler(args: dict) -> dict:
    """chip_rag_status: health check for all RAG backends."""
    from .local_tools import call_local
    return call_local("rag_status_op", args)




def _scheduler_status_handler(args: dict) -> dict:
    from .local_tools import call_local
    return call_local("scheduler_status_op", args)

def _scheduler_preload_handler(args: dict) -> dict:
    from .local_tools import call_local
    return call_local("scheduler_preload_op", args)

def _scheduler_cache_clear_handler(args: dict) -> dict:
    from .local_tools import call_local
    return call_local("scheduler_cache_clear_op", args)




def _post_rtl_methodology_handler(args: dict) -> dict:
    from .local_tools import call_local
    return call_local("post_rtl_methodology_op", args)




def _eda_route_handler(args: dict) -> dict:
    from .local_tools import call_local
    return call_local("eda_route_op", args)




def _dv_infra_handler(args: dict) -> dict:
    from .local_tools import call_local
    op_map = {"generate_tb": "dv_tb_generate_op", "test_plan": "dv_test_plan_op",
              "coverage": "dv_coverage_op", "sim_config": "dv_sim_config_op"}
    tool = op_map.get(args.get("op", ""), "dv_tb_generate_op")
    return call_local(tool, args)




def _examples_handler(args: dict) -> dict:
    """chip_examples: golden UVM TB example browsing (stdlib only)."""
    from . import examples_index
    op = args.get("op", "list")
    if op == "search":
        return examples_index.search(
            args["keyword"], category=args.get("category"),
            top_k=max(1, min(100, int(args.get("top_k") or 20))))
    if op == "get":
        return examples_index.get(args["path"])
    return examples_index.list_files(args.get("category"))


def _stats_handler(args: dict):
    ag = get_agent()
    if not ag.store:
        raise tool_error("config_missing", "CHIP_AGENT_DB not set")
    return {"stats": ag.store.skill_success_rate()}


def _skills_handler(args: dict):
    ag = get_agent()
    return {"summary": ag.registry.summary(), "domains": ag.registry.domains()}


def _domain_flows_handler(args: dict):
    # absolute imports: this file runs under a script entry point too
    from .domain_flows import (DOMAIN_FLOWS, pipeline_plan, flow as get_flow)
    d = args.get("domain")
    if d:
        f = get_flow(d)          # raises ValueError for unknown domains
        return {"ok": True, "domain": d, "stages": f.stages,
                "segments": f.segments,
                "loop_backs": [lb.__dict__ for lb in f.loop_backs],
                "escalations": [e.__dict__ for e in f.escalations],
                "signoff_gates": f.signoff_gates,
                "checkpoint_stage": f.checkpoint_stage,
                "tools": {"synopsys": f.tools_synopsys,
                          "cadence": f.tools_cadence,
                          "siemens": f.tools_siemens,
                          "utilities": f.tools_utilities},
                   "vendor_tool": f.vendor_tool}
    return {"ok": True, "domains": sorted(DOMAIN_FLOWS),
            "pipeline": pipeline_plan()}


def _infra_handler(args: dict):
    from .infra_detect import detect_tools
    return detect_tools()


# -- design pipeline (spec->tape-out state machine) -------------------------

def _stub_executor(domain: str, stage: str, attempt: int) -> dict:
    """Default executor: stages without supplied results are NOT RUN -> FAIL
    (reporting contract: never claim an unexecuted gate as PASS)."""
    return {"status": "FAIL", "failure_class": "tool_error",
            "notes": f"stage '{stage}' not executed in this session"}


def _results_executor(results: dict):
    def exec_(dom: str, stage: str, attempt: int) -> dict:
        return results.get(stage) or _stub_executor(dom, stage, attempt)
    return exec_


def _design_pipeline_handler(args: dict) -> dict:
    from .design_state import DesignState, DEFAULT_STATE_PATH
    from .design_pipeline import PipelineRunner, CrossDomainDriver
    op = args.get("op", "plan")
    state = DesignState(args.get("state") or DEFAULT_STATE_PATH)

    if op == "plan":
        from .domain_flows import pipeline_plan
        return {"ok": True, "pipeline": pipeline_plan()}
    if op == "status":
        return {"ok": True, **state.summary(),
                "history_tail": state.data["history"][-10:]}
    if op == "next":
        drv = CrossDomainDriver(state, _stub_executor)
        return {"ok": True, **drv.step()}
    if op == "re_verify":
        fr_id = args.get("fix_request_id")
        if not fr_id:
            return {"ok": False, "error": "fix_request_id is required"}
        drv = CrossDomainDriver(state, _results_executor(
            args.get("stage_results") or {}))
        return drv.re_verify(fr_id)
    if op == "run":
        domains = args.get("domains")
        if args.get("domain"):
            domains = [args["domain"]]
        runner = PipelineRunner(_results_executor(args.get("stage_results") or {}),
                                state, domains=domains)
        result = runner.run()
        return {"ok": result["decision"] != "escalate", **result}
    return {"ok": False, "error": f"unknown op: {op}"}



def _enhanced_plan_handler(args: dict) -> dict:
    """chip_agent_plan: route intent to best recipe + skill chain,
    enriched with UVM methodology and RAG context when applicable."""
    result = get_agent().plan(args["intent"])
    intent = args["intent"]
    lo = intent.lower()
    # Inject UVM methodology guidance
    if any(w in lo for w in ("driver", "monitor", "agent", "scoreboard",
                             "sequence", "env", "uvm", "testbench",
                             "factory", "objection", "tlm", "register")):
        try:
            from . import uvm_methodology as um
            m = um.methodology_checklist_for_intent(intent)
            if m.get("matched"):
                result["uvm_methodology"] = {
                    "best_pattern": m["best_pattern"],
                    "rationale": m.get("best_rationale", ""),
                    "checklist_level": m.get("checklist_level"),
                    "checklist": m.get("checklist", []),
                    "next_tools": m.get("pattern_data", {}).get("next_tools", []),
                }
        except Exception:
            pass
    # Inject RAG context for domain-specific queries
    if any(w in lo for w in ("compile", "simulation", "coverage", "debug",
                             "vcs", "verdi", "manual", "flow", "example")):
        try:
            from . import rag_router
            rag = rag_router.rag_search(intent, top_k=3)
            if rag.get("hits"):
                result["rag_context"] = {
                    "backends_used": rag.get("backends_used"),
                    "top_hits": [
                        {"source": h["source"], "kind": h["kind"],
                         "product": h["product"], "doc": h["doc"],
                         "score": h["score"], "text": h["text"][:500]}
                        for h in rag.get("hits", [])[:3]
                    ],
                    "recommendations": rag.get("recommendations", []),
                }
        except Exception:
            pass
    return result


TOOL_DEFS: list[ToolDef] = [
    ToolDef(
        name="chip_agent_plan",
        description="规划芯片验证/调试意图: 返回匹配 recipe、执行步骤、缺失技能与理由",
        schema={"type": "object",
                "properties": {"intent": {"type": "string"}},
                "required": ["intent"]},
        handler=_enhanced_plan_handler,
        annotations=_AN_RO, timeout=30.0,
    ),
    ToolDef(
        name="chip_agent_run",
        description="执行验证/调试工作流 (含生成 testbench + 强制 UVM 合规检查), 返回完整报告",
        schema={"type": "object",
                "properties": {"intent": {"type": "string"},
                               "out_dir": {"type": "string",
                                           "description": "testbench 生成输出目录 (可选)"}},
                "required": ["intent"]},
        handler=_run_handler,
        is_error=_run_report_is_error,
        render=lambda rep: rep.render(),
        annotations=_AN_MUT, step_progress=True,
    ),
    ToolDef(
        name="chip_generate_testbench",
        description="从 UVM 1800.2-2020.3.1 标准模板生成验证 testbench",
        schema={"type": "object",
                "properties": {"out_dir": {"type": "string"}},
                "required": []},
        handler=lambda a: call_local("generate_testbench", a),
        annotations=_AN_MUT,
    ),
    ToolDef(
        name="chip_check_uvm_compliance",
        description="检查 testbench 是否符合 UVM IEEE 1800.2-2020 (13 类静态规则, 生成后必须调用)",
        schema={"type": "object",
                "properties": {"root": {"type": "string",
                                        "description": "testbench 工程根目录"}},
                "required": ["root"]},
        handler=lambda a: call_local("check_uvm_compliance", a),
        is_error=_NOT_OK, annotations=_AN_RO, timeout=75.0, progress=True,
    ),
    ToolDef(
        name="chip_agent_skills",
        description="列出已注册技能与领域分布",
        schema={"type": "object", "properties": {}},
        handler=_skills_handler, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_agent_history",
        description="查询最近运行记录 (需 CHIP_AGENT_DB)",
        schema={"type": "object", "properties": {}},
        handler=_history_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_agent_stats",
        description="各技能成功率统计 (需 CHIP_AGENT_DB)",
        schema={"type": "object", "properties": {}},
        handler=_stats_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_edatools",
        description="发现 EDA 工具 (VCS/Verdi/NPI) 可用性: PATH + modulefile + 常见根, 缺失给 setup 指引; 并盘点本地 Accellera UVM 参考库 (6 版本 extracted/tarball/默认解析)",
        schema={"type": "object", "properties": {}},
        handler=lambda a: call_local("check_eda_tools", {}),
        annotations=_AN_RO, timeout=30.0,
    ),
    ToolDef(
        name="chip_run_simulation",
        description="VCS 编译+运行 UVM 仿真并解析 UVM 报告 (PASS/FAIL/error/fatal); 编译失败自动回退分析 comp.log 保根因; extra_args 透传站点验证过的 VCS 选项 (DPO/ICO 等 AI 增强不内置 flag, 防伪造厂商开关)",
        schema={"type": "object",
                "properties": {"root": {"type": "string", "description": "testbench 工程根目录"},
                               "testname": {"type": "string", "description": "+UVM_TESTNAME"},
                               "timeout": {"type": "integer", "description": "compile+run 总超时秒数"},
                               "extra_args": {"type": "array", "items": {"type": "string"},
                                              "description": "站点验证过的附加 VCS 编译 argv 参数；与仿真运行参数分开传递"}},
                "required": []},
        # degrade result carries its own ok/error (legacy semantics)
        handler=lambda a: call_local("run_simulation", a),
        annotations=_AN_MUT, timeout=660.0, progress=True,
    ),
    ToolDef(
        name="chip_open_waveform",
        description="Verdi 打开 FSDB 波形 (缺失时返回可复制命令)",
        schema={"type": "object",
                "properties": {"fsdb": {"type": "string"},
                               "signals": {"type": "array", "items": {"type": "string"}}},
                "required": ["fsdb"]},
        handler=lambda a: call_local("open_waveform", a),
        annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_analyze_eda_log",
        description="迭代分析 EDA log (三厂商全kind): 结构化问题+失败分类+下一步推荐; 失败时自动附 UG 手册步骤级指引",
        schema={"type": "object",
                "properties": {"log": {"type": "string", "description": "log 文件路径"},
                               "kind": {"type": "string", "description": "强制指定类型 (可选)"}},
                "required": []},
        handler=lambda a: call_local("analyze_eda_log", a),
        is_error=_NOT_OK, annotations=_AN_RO, timeout=30.0,
    ),
    ToolDef(
        name="chip_design_state",
        description="验证↔RTL 闭环 fix_request 状态机: summary/next(迭代上限+divergence)/open/claim/close/archive",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["summary", "next", "open", "claim", "close", "archive"]}},
                "required": ["op"]},
        handler=lambda a: call_local("design_state_pipeline", a),
        is_error=_NOT_OK, annotations=_AN_MUT,
    ),
    ToolDef(
        name="chip_memory_search",
        description="检索/写入域级经验记忆 (experiences.jsonl TF-IDF + knowledge 预览)",
        schema={"type": "object",
                "properties": {"domain": {"type": "string", "enum": DOMAIN_ENUM},
                               "query": {"type": "string"},
                               "limit": {"type": "integer"}},
                "required": ["query"]},
        handler=lambda a: call_local("search_domain_memory", a),
        is_error=_NOT_OK, annotations=_AN_MUT,
    ),
    ToolDef(
        name="chip_memory_distill",
        description="蒸馏域经验到 knowledge 摘要 (digital-agents memory-keeper)",
        schema={"type": "object",
                "properties": {"domain": {"type": "string", "enum": DOMAIN_ENUM},
                               "min_records": {"type": "integer"}},
                "required": []},
        handler=lambda a: call_local("memory_distill", a),
        is_error=_NOT_OK, annotations=_AN_MUT, timeout=75.0, progress=True,
    ),
    ToolDef(
        name="chip_agent_recall",
        description="主动记忆召回: 做任何事之前一次调用捞齐关于该意图的全部记忆 — 相关经验(按新近度/环境加权)、域蒸馏知识、域经验记录、有效步骤变体、技能风险与历史修复策略",
        schema={"type": "object",
                "properties": {"intent": {"type": "string"},
                               "domain": {"type": "string", "enum": DOMAIN_ENUM},
                               "limit": {"type": "integer"}},
                "required": ["intent"]},
        handler=_recall_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_qor_trends",
        description="跨 run QoR 指标趋势与回归检测 (qor_trends.py)",
        schema={"type": "object",
                "properties": {"design": {"type": "string"},
                               "domain": {"type": "string", "enum": DOMAIN_ENUM}},
                "required": ["design"]},
        handler=lambda a: call_local("memory_qor_trends", a),
        is_error=_NOT_OK, annotations=_AN_RO, timeout=75.0, progress=True,
    ),
    ToolDef(
        name="chip_design_pipeline",
        description="spec→tape-out 流水线引擎: plan(域序列)/status/run(执行域流或全流水线)/next(跨域闭环下一步)/re_verify(修复后复验)",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["plan", "status", "run", "next", "re_verify"]},
                               "domain": {"type": "string"},
                               "domains": {"type": "array", "items": {"type": "string"}},
                               "fix_request_id": {"type": "string"},
                               "stage_results": {"type": "object",
                                                 "description": "run 的外部阶段结果映射 {stage: {status,...}}"}},
                "required": ["op"]},
        handler=_design_pipeline_handler,
        is_error=_NOT_OK, annotations=_AN_MUT, progress=True,
    ),
    ToolDef(
        name="chip_domain_flows",
        description="16 域机器可读流程: 阶段序列/loop-back上限/sign-off门/checkpoint/工具路由",
        schema={"type": "object",
                "properties": {"domain": {"type": "string"}},
                "required": []},
        handler=_domain_flows_handler, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_infra_detect",
        description="EDA 环境检测: 仅 Synopsys/Cadence/Siemens 工具与独立列出的非 EDA 主机工具; 不安装、不部署 wrapper/MCP、不配置替代工具",
        schema={"type": "object", "properties": {}},
        handler=_infra_handler, annotations=_AN_RO, timeout=30.0,
    ),
    ToolDef(
        name="chip_flow_guide",
        description="芯片研发深度流程: 前端RTL→综合→后端→Signoff 四相 (阶段/输入输出产物/handoff判据/质量门/工具/跨相反馈环/经典坑); route 按 intent 定位相位与 recipe; capabilities 输出七项工程师能力↔agent机制↔工具矩阵; post_rtl_checklist 输出 RTL 仿真之后的深度签核检查项(LEC/GL-netlist/SDC/setup-hold/CDC-reset-lowpower-X/ECO等价/PPA回归) ↔ 域门映射",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["overview", "phase", "route",
                                               "capabilities",
                                               "post_rtl_checklist"]},
                               "phase": {"type": "string"},
                               "intent": {"type": "string"}},
                "required": ["op"]},
        handler=lambda a: call_local("flow_guide", a),
        is_error=_NOT_OK, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_ug_search",
        description="VCS+Verdi+UVM 官方手册向量检索 (哈希TF-IDF): 以章节/操作步骤为切分单元, 附 product/doc/chunk/section/kind 出处; kind=steps 可只命中操作步骤",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "product": {"type": "string",
                                           "enum": ["vcs", "verdi", "uvm"]},
                               "kind": {"type": "string",
                                        "enum": ["chapter", "steps", "prose"]},
                               "top_k": {"type": "integer"}},
                "required": ["query"]},
        handler=_ug_search_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_dvcon_search",
        description="DVCon US 2025/2026 论文语料向量检索 (哈希TF-IDF): 种子论文按 title/authors/venue/year/summary 建索引, 用户全文按段落/方法描述(method)/结论(conclusion)切分; kind/year 过滤, 支持检索失败分类→论文方法推荐",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "year": {"type": "string",
                                        "enum": ["2025", "2026"]},
                               "kind": {"type": "string",
                                        "enum": ["abstract", "method",
                                                 "conclusion", "paragraph"]},
                               "tag": {"type": "string",
                                       "enum": ["ai", "verification",
                                                "low-power", "cdc", "timing",
                                                "signoff", "stimulus"]},
                               "failure_class": {"type": "string"},
                               "top_k": {"type": "integer"}},
                "required": []},
        handler=_dvcon_search_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_rag_search",
        description="跨语料联邦 RAG 检索: 并行 fan-out 至 UG 手册/技术手册合并语料/DVCon 论文/金例子库, 单次查询返回统一溯源 schema (corpus/score/doc/kind/text), 单源故障或超时自动降级不影响其余源",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "sources": {"type": "array",
                                           "items": {"type": "string",
                                                     "enum": ["ug", "manual",
                                                              "dvcon",
                                                              "examples"]},
                                           "description": "默认全部四个语料源"},
                               "top_k": {"type": "integer"},
                               "timeout": {"type": "number"},
                               "product": {"type": "string"},
                               "kind": {"type": "string"},
                               "category": {"type": "string"}},
                "required": ["query"]},
        handler=lambda a: call_local("rag_search", a),
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_npi",
        description="Synopsys NPI C API 检索: 24 头文件/506 API (FSDB/覆盖率/UPF/VCS/NL/SDB/VerdiLearn); op=families 浏览族谱, op=search 关键词, op=get 精确签名",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["families", "search", "get"]},
                               "keyword": {"type": "string"},
                               "family": {"type": "string"},
                               "top_k": {"type": "integer"}},
                "required": ["op"]},
        handler=_npi_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_search",
        description="UVM 1.2 源码级正则检索 (221 类/2190 方法/458 宏/145 文件): 在真实 uvm_pkg 实现中定位符号/模式, 支持 file_filter/case_sensitive/上下文行数",
        schema={"type": "object",
                "properties": {"pattern": {"type": "string"},
                               "file_filter": {"type": "string"},
                               "case_sensitive": {"type": "boolean"},
                               "context_lines": {"type": "integer"},
                               "max_results": {"type": "integer"}},
                "required": ["pattern"]},
        handler=_uvm_search_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_class",
        description="UVM 1.2 类完整源码 (如 uvm_driver/uvm_reg_block): 返回文件位置头 + 类体全文",
        schema={"type": "object",
                "properties": {"class_name": {"type": "string"}},
                "required": ["class_name"]},
        handler=_uvm_class_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_hierarchy",
        description="UVM 1.2 类继承链: up=祖先链, down=直接子类, both=完整树",
        schema={"type": "object",
                "properties": {"class_name": {"type": "string"},
                               "direction": {"type": "string",
                                             "enum": ["up", "down", "both"]}},
                "required": ["class_name"]},
        handler=_uvm_hierarchy_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_methods",
        description="列出 UVM 1.2 类全部 function/task 签名 (virtual/static 修饰); 用前先发现方法名, 再取源码",
        schema={"type": "object",
                "properties": {"class_name": {"type": "string"}},
                "required": ["class_name"]},
        handler=_uvm_methods_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_method_source",
        description="UVM 1.2 指定方法的完整实现源码 (附文件/行号/注释头)",
        schema={"type": "object",
                "properties": {"class_name": {"type": "string"},
                               "method_name": {"type": "string"}},
                "required": ["class_name", "method_name"]},
        handler=_uvm_method_source_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_classes",
        description="浏览 UVM 1.2 全部类 (按子系统过滤, 如 reg/tlm/seq)",
        schema={"type": "object",
                "properties": {"filter": {"type": "string"}},
                "required": []},
        handler=_uvm_classes_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_file",
        description="UVM 1.2 源码文件带行号阅读 (relative_path 如 base/uvm_object.svh)",
        schema={"type": "object",
                "properties": {"relative_path": {"type": "string"},
                               "start_line": {"type": "integer"},
                               "end_line": {"type": "integer"}},
                "required": ["relative_path"]},
        handler=_uvm_file_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_files",
        description="UVM 1.2 源码文件树 (按子系统目录分组)",
        schema={"type": "object",
                "properties": {"directory_filter": {"type": "string"}},
                "required": []},
        handler=_uvm_files_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_macro",
        description="UVM 宏定义查询 (如 `uvm_object_utils/`uvm_field_int/`uvm_do, 带上下文)",
        schema={"type": "object",
                "properties": {"macro_name": {"type": "string"}},
                "required": ["macro_name"]},
        handler=_uvm_macro_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_semantic",
        description="UVM 1.2 语义检索 (哈希TF-IDF): 概念卡(2755 张蒸馏知识)+ 源码文档双路; 概念性问题优先用本工具",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "top_k": {"type": "integer"},
                               "source_only": {"type": "boolean"}},
                "required": ["query"]},
        handler=_uvm_semantic_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_explain",
        description="UVM 概念深度解析 (查询扩展: 源码 + 专家知识卡融合, 如 factory override/phase objection/config_db)",
        schema={"type": "object",
                "properties": {"concept": {"type": "string"}},
                "required": ["concept"]},
        handler=_uvm_explain_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_notes",
        description="UVM 1.2 源码深度分析笔记检索 (210 篇分析文件→1834 结构化单元): 按 base/seq/reg/tlm/comps/macros/factory/phase/config 等 15 个子系统索引; kind=steps/example/flow/prose/section 过滤",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "subsystem": {"type": "string"},
                               "kind": {"type": "string",
                                        "enum": ["steps", "example", "flow",
                                                 "prose", "section"]},
                               "top_k": {"type": "integer"}},
                "required": ["query"]},
        handler=_uvm_notes_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_examples",
        description="黄金 UVM TB 范例库 (Verification Academy uart_example: APB/UART/modem 三agent); op=list 按类浏览, op=search 文件名/内容检索, op=get 读源码片段",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["list", "search", "get"]},
                               "keyword": {"type": "string"},
                               "category": {"type": "string"},
                               "path": {"type": "string"},
                               "top_k": {"type": "integer"}},
                "required": ["op"]},
        handler=_examples_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_manual_search",
        description="技术手册全文检索 (VCS/Verdi/UVM/ChipStack 部署语料 + Synopsys/temp 合并语料, 235 册/427k 知识单元): 以章节/操作步骤/flow/示例为切分单元, 附 product/doc/kind/chapter/section 出处与原文片段",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "product": {"type": "string"},
                               "doc": {"type": "string"},
                               "kind": {"type": "string",
                                        "enum": ["chapter", "section", "steps",
                                                 "flow", "example", "prose"]},
                               "top_k": {"type": "integer"}},
                "required": ["query"]},
        handler=lambda a: call_local("manual_search", a),
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_manual_ingest",
        description="技术手册语料管线: op=scan 扫描候选, op=build 全量构建(提取→切分→SFT→向量索引), op=sft 仅生成语料, op=status 查看状态",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["scan", "build", "sft", "status"]},
                               "root": {"type": "string",
                                        "description": "recursive PDF/HTML scan root "
                                                       "(build/scan only)"},
                               "out": {"type": "string",
                                       "description": "corpus output root "
                                                      "(build/sft/status only)"}},
                "required": []},
        handler=lambda a: call_local("manual_ingest_op", a),
        is_error=lambda r: "error" in r,
        annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_uvm_methodology",
        description="UVM 1.2 方法学决策层: 组件模式(driver/monitor/agent/scoreboard/sequence/env/test/reg_model), phase 映射, TLM 连接, factory override, objection 生命周期, 验证清单; op=decide(query)/pattern(name)/phase_map/checklist(level)/pitfalls/patterns/full(query)",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["decide", "pattern", "phase_map",
                                               "checklist", "pitfalls", "patterns",
                                               "full"]},
                               "query": {"type": "string"},
                               "pattern": {"type": "string",
                                           "enum": ["driver", "monitor", "agent",
                                                    "scoreboard", "sequence", "env",
                                                    "test", "register_model",
                                                    "factory_override",
                                                    "objection_lifecycle",
                                                    "tlm_connection"]},
                               "level": {"type": "string",
                                         "enum": ["block_level", "subsystem_level",
                                                  "soc_level"]}},
                "required": []},
        handler=_uvm_methodology_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_rag_search",
        description="跨语料联邦 RAG 检索: 并行 fan-out 至 UG 手册/技术手册合并语料/DVCon 论文/UVM 方法学/UVM 语义概念卡/UVM 1.2 分析笔记(1834 单元)/NPI API, 单次查询返回统一溯源 schema (corpus/score/doc/kind/text), 单源故障或超时自动降级不影响其余源",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "backends": {"type": "array",
                                             "items": {"type": "string",
                                                       "enum": ["manual_search",
                                                                "uvm_methodology",
                                                                "uvm_semantic",
                                                                "uvm_notes",
                                                                "ug_index",
                                                                "dvcon_index",
                                                                "npi_index"]}},
                               "kind": {"type": "string"},
                               "product": {"type": "string"},
                               "top_k": {"type": "integer"}},
                "required": ["query"]},
        handler=_rag_search_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_rag_status",
        description="RAG 后端健康检查: 各索引可用性 + 测试命中数 + 可用工作流链",
        schema={"type": "object", "properties": {}, "required": []},
        handler=_rag_status_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_scheduler_status",
        description="调度器健康检查: 缓存命中率/熔断器状态/预热线程/依赖图/并行安全组",
        schema={"type": "object", "properties": {}, "required": []},
        handler=_scheduler_status_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_scheduler_preload",
        description="预热重索引: 后台预加载 UG/技术手册/UVM 语义向量索引, 消除首次查询冷启动延迟",
        schema={"type": "object",
                "properties": {"background": {"type": "boolean", "default": True}},
                "required": []},
        handler=_scheduler_preload_handler,
        is_error=lambda r: "error" in r,
    ),
    ToolDef(
        name="chip_scheduler_cache_clear",
        description="清除调度器结果缓存",
        schema={"type": "object", "properties": {}, "required": []},
        handler=_scheduler_cache_clear_handler,
    ),
    ToolDef(
        name="chip_post_rtl_methodology",
        description="RTL 仿真后 7 层验证方法学决策: LEC/GL-sim/SDC/STA/复位-CDC-UPF-Xprop/ECO等价/PPA回归. op=decide(query)/stage(name)/workflow/convergence(measurements)/pitfalls/stages/tool_chain/full(query)",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["decide", "stage", "workflow",
                                               "convergence", "pitfalls",
                                               "stages", "tool_chain", "full"]},
                               "query": {"type": "string"},
                               "stage": {"type": "string"},
                               "measurements": {"type": "object"}},
                "required": []},
        handler=_post_rtl_methodology_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_eda_route",
        description="EDA 工具路由验证: 意图→工具→命令模板 (compile/simv→VCS, fsdb→Verdi, CDC/lint→SpyGlass, SDC→PrimeTime, LEC→Formality). op=match(query)/validate(tool,command)/availability(tool)/routes/pitfalls(tool)",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["match", "validate", "availability",
                                               "routes", "pitfalls"]},
                               "query": {"type": "string"},
                               "tool": {"type": "string"},
                               "command": {"type": "array",
                                            "items": {"type": "string"}}},
                "required": []},
        handler=_eda_route_handler,
        is_error=lambda r: "error" in r, annotations=_AN_RO,
    ),
]

_DEF_BY_NAME = {d.name: d for d in TOOL_DEFS}

# Domain tags for client-side tool filtering. Kept in one map (not inline in
# 24 ToolDefs) so the grouping stays reviewable as a table; tools/list
# exposes it (legacy: "domain" key, SDK: "[domain: x]" description suffix —
# SDK ToolAnnotations is a strict pydantic model with no extension room).
_TOOL_DOMAINS = {
    "chip_uvm_search": "verification",
    "chip_uvm_class": "verification",
    "chip_uvm_hierarchy": "verification",
    "chip_uvm_methods": "verification",
    "chip_uvm_method_source": "verification",
    "chip_uvm_classes": "verification",
    "chip_uvm_file": "verification",
    "chip_uvm_files": "verification",
    "chip_uvm_macro": "verification",
    "chip_uvm_semantic": "verification",
    "chip_uvm_explain": "verification",
    "chip_uvm_notes": "verification",
    "chip_agent_plan": "orchestration",
    "chip_agent_run": "orchestration",
    "chip_generate_testbench": "verification",
    "chip_check_uvm_compliance": "verification",
    "chip_agent_skills": "meta",
    "chip_agent_history": "meta",
    "chip_agent_stats": "meta",
    "chip_edatools": "eda",
    "chip_run_simulation": "eda",
    "chip_open_waveform": "eda",
    "chip_analyze_eda_log": "eda",
    "chip_design_state": "design",
    "chip_design_pipeline": "design",
    "chip_domain_flows": "design",
    "chip_flow_guide": "design",
    "chip_infra_detect": "design",
    "chip_qor_trends": "design",
    "chip_memory_search": "memory",
    "chip_memory_distill": "memory",
    "chip_agent_recall": "memory",
    "chip_ug_search": "index",
    "chip_dvcon_search": "index",
    "chip_npi": "index",
    "chip_examples": "index",
    "chip_manual_search": "index",
    "chip_manual_ingest": "index",
    "chip_rag_search": "index",
    "chip_uvm_methodology": "verification",
    "chip_rag_search": "index",
    "chip_rag_status": "index",
    "chip_scheduler_status": "meta",
    "chip_scheduler_preload": "meta",
    "chip_scheduler_cache_clear": "meta",
    "chip_post_rtl_methodology": "design",
    "chip_eda_route": "eda",
    "chip_dv_infrastructure": "verification",
}
for _d in TOOL_DEFS:
    _d.domain = _TOOL_DOMAINS.get(_d.name, "general")


