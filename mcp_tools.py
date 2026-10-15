"""Single source of truth for the chip-ai-agent MCP tool surface.

TOOL_DEFS drives BOTH server modes so the two wire protocols can never
drift apart:

  - SDK mode (primary):  mcp_server.py imports the official MCP Python SDK v2
    and builds an MCPServer whose tools are code-generated from TOOL_DEFS —
    typed input validation, tool annotations, progress reporting, resources,
    prompts, streamable-HTTP.
  - Legacy mode (fallback): mcp_server.py runs a zero-dependency stdio
    JSON-RPC loop over the same TOOL_DEFS (no third-party imports).

This module itself must stay stdlib-only: `anyio` / `mcp` imports are kept
inside functions that only the SDK mode calls.
"""

from __future__ import annotations

import json
import os
import queue as _queue_mod
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .agent import AUTO_DISTILL_MIN_RECORDS, ChipAgent
from .local_tools import call_local
from . import metrics
from .planner import KeywordPlanner

# ---------------------------------------------------------------------------
# environment / paths (moved from mcp_server.py; same defaults, same vars)
# ---------------------------------------------------------------------------

SKILLS_DIR = os.environ.get("CHIP_AGENT_SKILLS",
                            str(Path(__file__).resolve().parent / "skills"))
_PLUGINS_DEFAULT = str(Path(__file__).resolve().parent / "digital" / "plugins")
EXTRA_SKILLS_DIRS = [
    d for d in os.environ.get("CHIP_AGENT_EXTRA_SKILLS", _PLUGINS_DEFAULT).split(":")
    if d and Path(d).exists()
]
_PKG_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get(
    "CHIP_AGENT_DB", str(_PKG_DIR / "chip_agent_runs.sqlite3"))
EXP_PATH = os.environ.get(
    "CHIP_AGENT_EXPERIENCE", str(_PKG_DIR / "experiences.jsonl"))

SERVER_NAME = "chip-ai-agent"
SERVER_VERSION = "2.0.0"   # SDK v2 architecture (1.3.0 was the stdlib loop)
SERVER_DESCRIPTION = (
    "Chip verification/debug agent: intent -> recipe -> skill/MCP tool chain "
    "-> report, with UVM compliance, EDA tool routing, cross-domain design "
    "pipeline and a domain experience memory."
)

# ---------------------------------------------------------------------------
# agent singleton (registry scan runs once per process)
# ---------------------------------------------------------------------------

_AGENT: ChipAgent | None = None
_AGENT_LOCK = threading.Lock()


def _make_planner():
    """Planner selection (Phase 3): CHIP_AGENT_PLANNER=llm|conversational
    wires the OpenAI-compatible planner in when an API key is present;
    anything else (or any failure) stays on the deterministic keyword
    planner. Without a key the LLM path would block 30s per call just to
    fall back, so it is never selected in that case."""
    mode = os.environ.get("CHIP_AGENT_PLANNER", "keyword")
    if mode in ("llm", "conversational"):
        try:
            from .planner import LLMPlanner, ConversationalPlanner
            llm = LLMPlanner(
                model=os.environ.get("CHIP_AGENT_LLM_MODEL", "gpt-4o-mini"),
                base_url=os.environ.get("CHIP_AGENT_LLM_BASE_URL",
                                        "https://api.openai.com/v1"),
                timeout=int(os.environ.get("CHIP_AGENT_LLM_TIMEOUT", "30")))
            if not llm.api_key:
                return KeywordPlanner()
            if mode == "conversational":
                return ConversationalPlanner(llm)
            return llm
        except Exception:
            pass
    return KeywordPlanner()


def get_agent() -> ChipAgent:
    global _AGENT
    if _AGENT is None:
        with _AGENT_LOCK:
            if _AGENT is None:
                _AGENT = ChipAgent(
                    SKILLS_DIR if Path(SKILLS_DIR).exists() else "/nonexistent",
                    db_path=DB_PATH or None,
                    experience_path=EXP_PATH or None,
                    extra_skills_dirs=EXTRA_SKILLS_DIRS or None,
                    planner=_make_planner(),
                )
    return _AGENT


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


def _json_text(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@dataclass
class ToolError(Exception):
    """Uniform tool-error contract shared by legacy + SDK dispatch.

    code       — stable machine-readable error class (e.g. "unknown_tool",
                 "timeout", "invalid_params", "internal")
    message    — human-readable detail (str(exc) stays backward compatible)
    retryable  — client hint: is re-invoking the same call likely to succeed
    """
    code: str = "internal"
    message: str = ""
    retryable: bool = False

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def payload(self) -> dict:
        """Structured error body; keeps the legacy top-level "error" key."""
        return {"error": self.message, "error_code": self.code,
                "retryable": self.retryable}


def tool_error(code: str, message: str, retryable: bool = False) -> ToolError:
    """Construct a ToolError; single place both dispatch paths use."""
    return ToolError(code=code, message=message, retryable=retryable)


def _run_report_is_error(rep) -> bool:
    return any(not s.ok for s in rep.steps) or not rep.steps


def _run_handler(args: dict, progress_cb=None):
    """chip_agent_run: everything except `intent` is the run context."""
    ctx = {k: v for k, v in args.items() if k != "intent"} or None
    return get_agent().run(args["intent"], context=ctx, progress_cb=progress_cb)


def _history_handler(args: dict):
    ag = get_agent()
    if not ag.store:
        return {"error": "CHIP_AGENT_DB not set"}
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
        except Exception as e:                 # memory is best-effort
            out["domain_memory_error"] = str(e)
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
    return out


def _ug_search_handler(args: dict) -> dict:
    """chip_ug_search: VCS+Verdi UG vector retrieval (stdlib+numpy only)."""
    from . import ug_index
    return ug_index.search(
        args["query"],
        product=args.get("product"),
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
        return {"error": "CHIP_AGENT_DB not set"}
    return {"stats": ag.store.skill_success_rate()}


def _skills_handler(args: dict):
    ag = get_agent()
    return {"summary": ag.registry.summary(), "domains": ag.registry.domains()}


def _wrappers_handler(args: dict):
    if args.get("tool"):
        return call_local("run_eda_wrapper", args)
    return call_local("list_eda_wrappers", args)


def _domain_flows_handler(args: dict):
    # absolute imports: this file runs under a script entry point too
    from .domain_flows import (DOMAIN_FLOWS, pipeline_plan, flow as get_flow)
    d = args.get("domain")
    if d:
        f = get_flow(d)          # raises ValueError for unknown domains
        return {"ok": True, "domain": d, "stages": f.stages,
                "loop_backs": [lb.__dict__ for lb in f.loop_backs],
                "escalations": [e.__dict__ for e in f.escalations],
                "signoff_gates": f.signoff_gates,
                "checkpoint_stage": f.checkpoint_stage,
                "tools": {"oss": f.tools_oss,
                          "proprietary": f.tools_proprietary,
                          "wrapper": f.wrapper}}
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


TOOL_DEFS: list[ToolDef] = [
    ToolDef(
        name="chip_agent_plan",
        description="规划芯片验证/调试意图: 返回匹配 recipe、执行步骤、缺失技能与理由",
        schema={"type": "object",
                "properties": {"intent": {"type": "string"}},
                "required": ["intent"]},
        handler=lambda a: get_agent().plan(a["intent"]),
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
        description="VCS 编译+运行 UVM 仿真并解析 UVM 报告 (PASS/FAIL/error/fatal)",
        schema={"type": "object",
                "properties": {"root": {"type": "string", "description": "testbench 工程根目录"},
                               "testname": {"type": "string", "description": "+UVM_TESTNAME"}},
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
        description="迭代分析 EDA log (VCS编译/UVM仿真/Verdi/LSF): 结构化问题+失败分类+下一步推荐",
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
                "properties": {"domain": {"type": "string"},
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
                "properties": {"domain": {"type": "string"},
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
                               "domain": {"type": "string"},
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
                               "domain": {"type": "string"}},
                "required": ["design"]},
        handler=lambda a: call_local("memory_qor_trends", a),
        is_error=_NOT_OK, annotations=_AN_RO, timeout=75.0, progress=True,
    ),
    ToolDef(
        name="chip_eda_wrappers",
        description="列出/运行 digital-agents 输出压缩 wrapper (verilator/yosys/openroad/...): 大日志→紧凑JSON, exit 0 ≠ pass",
        schema={"type": "object",
                "properties": {"tool": {"type": "string"},
                               "args": {"type": "array", "items": {"type": "string"}},
                               "timeout": {"type": "integer"}},
                "required": []},
        handler=_wrappers_handler,
        is_error=lambda r: "error" in r, annotations=_AN_MUT, timeout=320.0, progress=True,
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
        description="基础设施对齐检测: 24 开源工具 + 7 商用工具(detect-only) + wrapper/MCP 部署状态",
        schema={"type": "object", "properties": {}},
        handler=_infra_handler, annotations=_AN_RO, timeout=30.0,
    ),
    ToolDef(
        name="chip_flow_guide",
        description="芯片研发深度流程: 前端RTL→综合→后端→Signoff 四相 (阶段/输入输出产物/handoff判据/质量门/工具/跨相反馈环/经典坑); route 按 intent 定位相位与 recipe",
        schema={"type": "object",
                "properties": {"op": {"type": "string",
                                      "enum": ["overview", "phase", "route"]},
                               "phase": {"type": "string"},
                               "intent": {"type": "string"}},
                "required": ["op"]},
        handler=lambda a: call_local("flow_guide", a),
        is_error=_NOT_OK, annotations=_AN_RO,
    ),
    ToolDef(
        name="chip_ug_search",
        description="VCS+Verdi 官方 UG 手册向量检索 (哈希TF-IDF): 按语义查询命中文档段落, 附 product/doc/chunk 出处",
        schema={"type": "object",
                "properties": {"query": {"type": "string"},
                               "product": {"type": "string",
                                           "enum": ["vcs", "verdi"]},
                               "top_k": {"type": "integer"}},
                "required": ["query"]},
        handler=_ug_search_handler,
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
]

_DEF_BY_NAME = {d.name: d for d in TOOL_DEFS}

# Domain tags for client-side tool filtering. Kept in one map (not inline in
# 24 ToolDefs) so the grouping stays reviewable as a table; tools/list
# exposes it (legacy: "domain" key, SDK: "[domain: x]" description suffix —
# SDK ToolAnnotations is a strict pydantic model with no extension room).
_TOOL_DOMAINS = {
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
    "chip_eda_wrappers": "eda",
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
    "chip_npi": "index",
    "chip_examples": "index",
}
for _d in TOOL_DEFS:
    _d.domain = _TOOL_DOMAINS.get(_d.name, "general")


def render_result(d: ToolDef, res: Any) -> str:
    if d.render is not None:
        return d.render(res)
    return _json_text(res)


# ---------------------------------------------------------------------------
# legacy-mode dispatch (zero-dependency; used by mcp_server.py fallback loop)
# ---------------------------------------------------------------------------

def tools_schema() -> list[dict]:
    """tools/list payload for the legacy loop (same wire shape as before)."""
    return [{"name": d.name, "description": d.description,
             "domain": d.domain,
             "inputSchema": d.schema} for d in TOOL_DEFS]


def call_tool(name: str, args: dict) -> dict:
    """Legacy tools/call dispatch; returns {content: [...], isError: bool}."""
    d = _DEF_BY_NAME.get(name)
    if d is None:
        err = tool_error("unknown_tool", f"unknown tool: {name}")
        return {"content": [{"type": "text", "text": _json_text(err.payload())}],
                "isError": True}
    try:
        _t0 = time.perf_counter()
        res = d.handler(args)
        metrics.record(name, (time.perf_counter() - _t0) * 1000,
                       d.is_error(res))
    except ToolError as e:
        metrics.record(name, 0.0, True)
        return {"content": [{"type": "text", "text": _json_text(e.payload())}],
                "isError": True}
    except Exception as e:
        metrics.record(name, (time.perf_counter() - _t0) * 1000, True)
        err = tool_error("internal", str(e), retryable=True)
        return {"content": [{"type": "text", "text": _json_text(err.payload())}],
                "isError": True}
    return {"content": [{"type": "text", "text": render_result(d, res)}],
            "isError": d.is_error(res)}

def _boot_audit() -> None:
    """Boot-time health inspection for long-running (streamable-HTTP)
    deployments: audits memory/DB read-only, and flags domains whose
    experience files have outgrown their distilled knowledge (a proactive
    "distill recommended" hint instead of a slow subprocess at boot).
    Runs in the lifespan worker thread; failures surface in the server
    log, never on the wire."""
    import logging
    _log = logging.getLogger("chip_ai_agent.learning")
    try:
        ag = get_agent()
        notes = []
        if ag.experience:
            from .data_quality import audit_experience
            notes.append(f"experience: {audit_experience(str(ag.experience.path))}")
        if ag.store:
            from .data_quality import audit_db
            notes.append(f"db: {audit_db(str(ag.store.path))}")
        _log.info("boot audit: %s", " | ".join(notes))
        # growth check: experiences.jsonl newer than knowledge.md -> distill hint
        try:
            from .digital_memory import DomainMemory, VALID_DOMAINS
            stale = []
            for domain in VALID_DOMAINS:
                mem = DomainMemory(domain)
                jl, kd = mem.jsonl, mem.dir / "knowledge.md"
                if jl.exists() and kd.exists() and \
                        jl.stat().st_mtime > kd.stat().st_mtime:
                    n = len(mem.records())
                    if n >= AUTO_DISTILL_MIN_RECORDS:
                        stale.append(f"{domain}({n})")
            if stale:
                _log.info("distill recommended (knowledge older than "
                          "experiences): %s", ", ".join(stale))
        except Exception:
            _log.debug("growth check skipped", exc_info=True)
    except Exception:
        _log.exception("boot audit failed (best-effort)")



def build_sdk_server():
    """Lazy re-export: real implementation lives in sdk_server.py."""
    from .sdk_server import build_sdk_server as _b
    return _b()


def transport_config() -> tuple[str, dict]:
    """Lazy re-export: real implementation lives in sdk_server.py."""
    from .sdk_server import transport_config as _t
    return _t()


_SDK_PRIVATE = {
    "_TYPE_MAP", "_schema_annotation", "_make_sdk_fn", "_STEP_DONE",
    "_TOOL_CACHE", "_TOOL_CACHE_LOCK", "_tool_cache_ttl",
    "_tool_cache_get", "_tool_cache_put", "_sdk_call",
    "_run_with_step_progress", "_make_lifespan",
}


def __getattr__(name: str):
    """PEP 562: forward SDK-mode private names to sdk_server so existing
    tests/callers that poke mcp_tools._TOOL_CACHE keep working after the
    module split."""
    if name in _SDK_PRIVATE:
        import importlib
        mod = importlib.import_module("chip_ai_agent.sdk_server")
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
