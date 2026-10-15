"""SDK-mode MCPServer v2 construction (split from mcp_tools.py).

Everything here requires the official mcp SDK; the legacy stdio fallback in
mcp_server.py never imports this module. Domain logic (TOOL_DEFS, handlers,
resources data sources) stays in mcp_tools — this module is protocol
scaffolding only: pydantic code-gen, server-side TTL cache, progress
plumbing, lifespan, and server assembly.
"""
from __future__ import annotations

import os
import queue as _queue_mod
import threading
import time
import logging
from typing import Any, Callable

from . import metrics
from .mcp_tools import (SERVER_NAME, SERVER_DESCRIPTION, SERVER_VERSION,
                        TOOL_DEFS, _DEF_BY_NAME, _json_text, render_result,
                        ToolDef, _boot_audit, get_agent)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SDK mode: MCPServer v2 construction
# (anyio/mcp imports stay inside functions — legacy mode is stdlib-only)
# ---------------------------------------------------------------------------

_TYPE_MAP = {"string": "str", "integer": "int", "boolean": "bool"}


def _schema_annotation(spec: dict) -> str:
    """JSON-schema property -> type annotation source string (SDK code-gen)."""
    t = spec.get("type")
    if t in _TYPE_MAP:
        base = _TYPE_MAP[t]
    elif t == "array":
        return f"t.List[{_schema_annotation(spec.get('items', {'type': 'string'}))}]"
    elif t == "object":
        return "t.Dict"
    else:
        base = "str"
    enum = spec.get("enum")
    if enum and len(enum) <= 12 and all(isinstance(v, str) for v in enum):
        return f"t.Literal[{', '.join(repr(v) for v in enum)}]"
    return base


def _make_sdk_fn(d: ToolDef) -> Callable:
    """Code-generate an async handler with a typed signature matching d.schema.

    The SDK derives the pydantic input model from the signature, so the
    generated annotation is the validation contract; ctx is injected by the
    SDK's Context mechanism (typing.get_type_hints resolves against the exec
    namespace, which therefore must contain Context/t/ToolError names).
    """
    import typing
    from mcp.server.mcpserver import Context

    props = d.schema.get("properties") or {}
    required = set(d.schema.get("required") or [])
    params, collects = [], []
    for pname, spec in props.items():
        default = "" if pname in required else " = None"
        params.append(f"{pname}: {_schema_annotation(spec)}{default}")
        collects.append(f'    if {pname} is not None: _args["{pname}"] = {pname}')
    params.append("ctx: Context = None")
    body = "\n".join(collects) or "    pass"
    src = (
        f"async def f(*, {', '.join(params)}) -> str:\n"
        f"    _args = {{}}\n{body}\n"
        f"    return await _sdk_call(_DEF_BY_NAME[{d.name!r}], _args, ctx)\n"
    )
    ns = dict(globals())
    ns.update({"t": typing, "Context": Context})
    exec(src, ns)
    return ns["f"]


_STEP_DONE = object()


# Server-side TTL cache for read-only, non-progress tool results. These tools
# re-scan registries/files on every call; a short-lived memo makes repeated
# agent polls cheap without risking stale data for mutating/long operations.
_TOOL_CACHE: dict[str, tuple[float, str]] = {}
_TOOL_CACHE_LOCK = threading.Lock()


def _tool_cache_ttl() -> float:
    try:
        return max(0.0, float(os.environ.get("CHIP_AGENT_TOOL_CACHE_TTL", "30")))
    except ValueError:
        return 30.0


def _tool_cache_get(key: str) -> str | None:
    ttl = _tool_cache_ttl()
    if ttl <= 0:
        return None
    with _TOOL_CACHE_LOCK:
        hit = _TOOL_CACHE.get(key)
        if hit is None:
            return None
    at, rendered = hit
    if time.monotonic() - at > ttl:
        with _TOOL_CACHE_LOCK:
            _TOOL_CACHE.pop(key, None)
        return None
    return rendered


def _tool_cache_put(key: str, rendered: str) -> None:
    if _tool_cache_ttl() <= 0:
        return
    with _TOOL_CACHE_LOCK:
        _TOOL_CACHE[key] = (time.monotonic(), rendered)
        # keep the memo bounded: drop the oldest quarter when oversized
        if len(_TOOL_CACHE) > 256:
            for k in sorted(_TOOL_CACHE, key=lambda k: _TOOL_CACHE[k][0])[:64]:
                _TOOL_CACHE.pop(k, None)


async def _sdk_call(d: ToolDef, args: dict, ctx) -> str:
    """Run one tool from an SDK handler; ToolError carries isError semantics."""
    import anyio
    from mcp.server.mcpserver.exceptions import ToolError

    from .mcp_tools import tool_error

    cacheable = (d.annotations.get("read_only_hint")
                 and not d.progress and not d.step_progress)
    ckey = ""
    if cacheable:
        try:
            ckey = _json_text([d.name, args])
        except (TypeError, ValueError):
            cacheable = False
        else:
            hit = _tool_cache_get(ckey)
            if hit is not None:
                metrics.record_cache_hit()
                return hit
    if d.progress and not d.step_progress:
        # no message= kwarg: ProgressNotification.message only exists on
        # protocol >= 2025-03-26 and we negotiate down to 2024-11-05.
        await ctx.report_progress(0.0, 1.0)
    try:
        _t0 = time.perf_counter()
        if d.step_progress:
            res = await _run_with_step_progress(d, args, ctx)
        elif d.timeout:
            with anyio.move_on_after(d.timeout) as scope:
                res = await anyio.to_thread.run_sync(d.handler, args)
            if scope.cancel_called:
                err = tool_error("timeout",
                                 f"{d.name}: timed out after {d.timeout}s "
                                 f"(operation may still finish in the background)",
                                 retryable=True)
                raise ToolError(_json_text(err.payload())) from err
        else:
            res = await anyio.to_thread.run_sync(d.handler, args)
    except Exception as e:
        metrics.record(d.name, (time.perf_counter() - _t0) * 1000, True)
        # uniform with legacy mode: structured {error, error_code, retryable}
        err = tool_error("internal", str(e), retryable=True)
        raise ToolError(_json_text(err.payload())) from err
    metrics.record(d.name, (time.perf_counter() - _t0) * 1000,
                   d.is_error(res))
    if d.progress and not d.step_progress:
        await ctx.report_progress(1.0, 1.0)

    if d.is_error(res):
        raise ToolError(render_result(d, res))
    rendered = render_result(d, res)
    if cacheable:
        _tool_cache_put(ckey, rendered)
    return rendered


async def _run_with_step_progress(d: ToolDef, args: dict, ctx) -> Any:
    """Stream per-step progress while the blocking run executes in a thread.

    The target is exception-safe: whatever happens it signals DONE exactly
    once, so the drain loop can never block forever and the error surfaces
    as the tool result (or via _sdk_call's ToolError wrap) instead of a
    bare task-group ExceptionGroup.
    """
    import anyio

    q: _queue_mod.Queue = _queue_mod.Queue()

    def target() -> None:
        try:
            res = d.handler(args, lambda i, n, label: q.put((i, n, label)))
        except Exception as e:                       # keep the real message
            res = e
        q.put((_STEP_DONE, res))

    res: Any = None
    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, target)
        while True:
            item = await anyio.to_thread.run_sync(q.get)
            if item[0] is _STEP_DONE:
                res = item[1]
                break
            i, n, label = item
            await ctx.report_progress(float(i), float(n))
    if isinstance(res, Exception):
        raise res
    return res



def _make_lifespan(warm: bool):
    """Lifespan manager; warms the agent singleton at boot for shared
    (streamable-HTTP) deployments so every first caller hits a hot registry,
    then runs the boot-time memory/DB audit."""
    from contextlib import asynccontextmanager
    import anyio

    @asynccontextmanager
    async def lifespan(srv):
        if warm:
            await anyio.to_thread.run_sync(get_agent)
            await anyio.to_thread.run_sync(_boot_audit)
        yield {}
    return lifespan


# -- resources (read-only views over existing domain functions) -------------


def _resource_skills() -> str:
    ag = get_agent()
    return _json_text({"summary": ag.registry.summary(),
                       "domains": ag.registry.domains()})


def _resource_skills_domain(domain: str) -> str:
    from mcp.server.mcpserver.exceptions import ResourceNotFoundError
    doms = get_agent().registry.domains()
    if domain not in doms:
        raise ResourceNotFoundError(f"unknown skill domain: {domain}")
    return _json_text({domain: doms[domain]})


def _resource_runs() -> str:
    ag = get_agent()
    if not ag.store:
        return _json_text({"error": "CHIP_AGENT_DB not set"})
    return _json_text({"history": ag.store.history()})


def _resource_design_state() -> str:
    from .design_state import DesignState, DEFAULT_STATE_PATH
    return _json_text(DesignState(DEFAULT_STATE_PATH).summary())


def _resource_flow(domain: str) -> str:
    from mcp.server.mcpserver.exceptions import ResourceNotFoundError
    from .domain_flows import DOMAIN_FLOWS
    if domain not in DOMAIN_FLOWS:
        raise ResourceNotFoundError(f"unknown domain: {domain}")
    f = DOMAIN_FLOWS[domain]
    return _json_text({"domain": domain, "stages": f.stages,
                       "loop_backs": [lb.__dict__ for lb in f.loop_backs],
                       "escalations": [e.__dict__ for e in f.escalations],
                       "signoff_gates": f.signoff_gates,
                       "checkpoint_stage": f.checkpoint_stage,
                       "tools": {"oss": f.tools_oss,
                                 "proprietary": f.tools_proprietary,
                                 "wrapper": f.wrapper}})


def _resource_memory(domain: str) -> str:
    """chip://memory/{domain} — distilled knowledge + learned skill chains."""
    from mcp.server.mcpserver.exceptions import ResourceNotFoundError
    from .digital_memory import VALID_DOMAINS, DomainMemory
    if domain not in VALID_DOMAINS:
        raise ResourceNotFoundError(f"unknown memory domain: {domain}")
    mem = DomainMemory(domain)
    parts = []
    knowledge = mem.knowledge()
    if knowledge:
        parts.append("# Distilled knowledge\n\n" + knowledge)
    variants = mem.plan_variants(limit=10)
    if variants:
        parts.append("# Effective skill chains (agent-learned)\n\n"
                     + "\n".join(f"- {v['recipe']}: {' -> '.join(v['skills'])} "
                                 f"(x{v.get('successes', 1)})" for v in variants))
    if not parts:
        return _json_text({"domain": domain,
                           "note": "no knowledge or variants recorded yet"})
    return "\n\n".join(parts)


def _resource_guide() -> str:
    return _json_text(call_local("flow_guide", {"op": "overview"}))


def _resource_ug() -> str:
    """chip://ug — UG vector index status."""
    from . import ug_index
    return _json_text(ug_index.index_status())


def _resource_npi() -> str:
    """chip://npi — NPI API family overview."""
    from . import npi_index
    return _json_text(npi_index.families())


def _resource_examples() -> str:
    """chip://examples — golden TB example category overview."""
    from . import examples_index
    return _json_text(examples_index.list_files())


def _resource_metrics() -> str:
    """chip://metrics — in-process tool-call counters (dual-protocol)."""
    return _json_text(metrics.snapshot())


# -- prompts -----------------------------------------------------------------

def _prompt_plan() -> str:
    return (
        "你是芯片验证/调试规划助手。请先让用户描述其验证或调试意图"
        "(例如 UVM scoreboard 比对失败、VCS 编译错误、FSDB 波形定位),"
        "然后调用 chip_agent_plan 工具获取匹配的 recipe 与执行步骤,"
        "确认步骤完整后调用 chip_agent_run 执行。若涉及 testbench 生成,"
        "生成后必须调用 chip_check_uvm_compliance 做 IEEE 1800.2-2020 合规检查。"
    )


def _prompt_debug() -> str:
    return (
        "芯片调试工作流: 0) 先用 chip_agent_recall 主动召回关于该问题的全部记忆"
        "(历史经验/域知识/有效变体/风险策略); 1) 用 chip_analyze_eda_log 分析日志并拿到失败分类与"
        "重试策略; 2) 用 chip_agent_plan 规划修复 recipe; 3) 用 chip_agent_run "
        "执行; 4) 若失败,用 chip_design_state 打开 fix_request 走验证↔RTL 闭环;"
        " 5) 用 chip_open_waveform 打开 FSDB 定位根因; 6) 用 chip_memory_search "
        "检索历史经验。每个阶段的结果都会写入报告库供复盘。"
    )


def build_sdk_server():
    """Construct the MCPServer (SDK mode). Raises ImportError without mcp."""
    import anyio  # noqa: F401  (validates the dependency early)
    from mcp.server.mcpserver import MCPServer, Context  # noqa: F401
    from mcp.server.caching import CACHEABLE_METHODS, CacheHint
    from mcp.types import ToolAnnotations  # noqa: F401

    warm = os.environ.get("CHIP_AGENT_TRANSPORT", "stdio") != "stdio"
    srv = MCPServer(
        SERVER_NAME,
        title="Chip AI Agent",
        description=SERVER_DESCRIPTION,
        instructions=(
            "chip_ai_agent 是芯片验证/调试工作流引擎。读取型工具已标注 "
            "readOnlyHint,可安全并行调用;chip_agent_run 等长操作会上报进度。"),
        version=SERVER_VERSION,
        lifespan=_make_lifespan(warm),
        # SEP-2549: advertise client-side freshness for listing/read methods.
        cache_hints={m: CacheHint(ttl_ms=60_000, scope="private")
                     for m in CACHEABLE_METHODS},
    )

    for d in TOOL_DEFS:
        ann = ToolAnnotations(**d.annotations)
        srv.tool(name=d.name,
                 description=f"{d.description} [domain: {d.domain}]",
                 annotations=ann, structured_output=False)(_make_sdk_fn(d))

    srv.resource("chip://skills", description="全部已注册技能与领域分布")(_resource_skills)
    srv.resource("chip://skills/{domain}", description="单领域技能清单")(_resource_skills_domain)
    srv.resource("chip://runs", description="最近运行记录 (report store)")(_resource_runs)
    srv.resource("chip://design/state", description="design_state.json 摘要")(_resource_design_state)
    srv.resource("chip://flows/{domain}", description="单域机器可读流程")(_resource_flow)
    srv.resource("chip://memory/{domain}", description="单域蒸馏知识 + 学习到的有效技能链")(_resource_memory)
    srv.resource("chip://guide", description="四相芯片研发流程总览")(_resource_guide)
    srv.resource("chip://ug", description="UG 向量索引状态 (文档数/chunk 数/大小)")(_resource_ug)
    srv.resource("chip://npi", description="NPI C API 族谱总览 (24 头文件/506 API)")(_resource_npi)
    srv.resource("chip://examples", description="黄金 UVM TB 范例分类总览 (uart_example)")(_resource_examples)
    srv.resource("chip://metrics", description="工具调用指标 (次数/延迟/错误率/缓存命中)")(_resource_metrics)

    srv.prompt("chip-plan", description="芯片验证/调试任务规划提示词")(_prompt_plan)
    srv.prompt("chip-debug", description="芯片调试多步工作流提示词")(_prompt_debug)

    return srv


def transport_config() -> tuple[str, dict]:
    """Transport selection for mcp.run(): stdio (default) or streamable-http."""
    transport = os.environ.get("CHIP_AGENT_TRANSPORT", "stdio")
    if transport in ("streamable-http", "http"):
        return "streamable-http", {
            "host": os.environ.get("CHIP_AGENT_HOST", "127.0.0.1"),
            "port": int(os.environ.get("CHIP_AGENT_PORT", "8000")),
            "stateless_http": os.environ.get("CHIP_AGENT_STATELESS", "") == "1",
        }
    return "stdio", {}
