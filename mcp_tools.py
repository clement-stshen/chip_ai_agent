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
import shlex
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import AUTO_DISTILL_MIN_RECORDS, ChipAgent
from .local_tools import call_local
from . import metrics
from .planner import KeywordPlanner
from .tool_registry import (  # noqa: F401  (re-exported for compat)
    _AN_MUT, _AN_RO, _DEF_BY_NAME, _design_pipeline_handler,
    _domain_flows_handler, _examples_handler, _FALSE, _history_handler,
    _infra_handler, _NOT_OK, _npi_handler, _recall_handler,
    _results_executor, _run_handler, _run_report_is_error, _skills_handler,
    _stats_handler, _stub_executor, _TOOL_DOMAINS, _ug_search_handler,
    ToolDef, TOOL_DEFS,
)

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


def _external_server_command() -> list[str] | None:
    """External MCP server for registry-skill dispatch — same contract as
    `python -m chip_ai_agent.cli --server CMD...` (space-separated argv).
    Empty/unset -> None: registry skills are then reported as *missing* by
    the planner instead of failing every step with
    "no MCP server configured"."""
    raw = os.environ.get("CHIP_AGENT_EXTERNAL_SERVER", "")
    return shlex.split(raw) if raw.strip() else None


def get_agent() -> ChipAgent:
    global _AGENT
    if _AGENT is None:
        with _AGENT_LOCK:
            if _AGENT is None:
                _AGENT = ChipAgent(
                    SKILLS_DIR if Path(SKILLS_DIR).exists() else "/nonexistent",
                    mcp_command=_external_server_command(),
                    db_path=DB_PATH or None,
                    experience_path=EXP_PATH or None,
                    extra_skills_dirs=EXTRA_SKILLS_DIRS or None,
                    planner=_make_planner(),
                )
    return _AGENT


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


APP_ERROR_CODE = "tool_reported_error"


def _app_error_envelope(res: Any) -> dict:
    """Step 25 (audit A2): handler-level error results ({"ok": false, ...})
    must carry the same machine contract as transport errors. The original
    payload is preserved under "result" so human readers lose nothing."""
    msg = ""
    if isinstance(res, dict):
        msg = str(res.get("error") or res.get("reason") or "")
    return {"error": msg or "tool reported an error result",
            "error_code": APP_ERROR_CODE,
            "retryable": False,           # deterministic tool result: same
            "result": res}                # inputs will fail the same way


def _run_handler_with_timeout(d: ToolDef, args: dict) -> Any:
    """Step 25 (audit A3): enforce ToolDef.timeout in legacy mode too.

    The worker thread may still finish in the background (same semantics as
    the SDK path); the client, however, gets the structured timeout error
    instead of a hung stdio connection.
    """
    if d.timeout is None:
        return d.handler(args)
    import threading as _th
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["res"] = d.handler(args)
        except BaseException as e:       # re-raised on the caller side
            box["err"] = e

    t = _th.Thread(target=_target, daemon=True, name="mcp-legacy-tool")
    t.start()
    t.join(d.timeout)
    if t.is_alive():
        raise TimeoutError(
            f"{d.name}: timed out after {d.timeout}s "
            "(operation may still finish in the background)")
    if "err" in box:
        raise box["err"]
    return box.get("res")


def render_result(d: ToolDef, res: Any) -> str:
    if d.render is not None:
        return d.render(res)
    return _json_text(res)


# ---------------------------------------------------------------------------
# legacy-mode dispatch (zero-dependency; used by mcp_server.py fallback loop)
# ---------------------------------------------------------------------------

def tools_schema(domain: str | None = None) -> list[dict]:
    """tools/list payload for the legacy loop (same wire shape as before).

    domain — optional server-side filter; unknown domain yields [] so the
    client sees an explicit empty result instead of silently getting all.
    """
    return [{"name": d.name, "description": d.description,
             "domain": d.domain,
             "inputSchema": d.schema} for d in TOOL_DEFS
            if domain is None or d.domain == domain]


def call_tool(name: str, args: dict) -> dict:
    """Legacy tools/call dispatch; returns {content: [...], isError: bool}."""
    d = _DEF_BY_NAME.get(name)
    if d is None:
        err = tool_error("unknown_tool", f"unknown tool: {name}")
        return {"content": [{"type": "text", "text": _json_text(err.payload())}],
                "isError": True}
    _t0 = time.perf_counter()          # audit A4: duration for every path
    try:
        res = _run_handler_with_timeout(d, args)
        metrics.record(name, (time.perf_counter() - _t0) * 1000,
                       d.is_error(res))
    except ToolError as e:
        metrics.record(name, (time.perf_counter() - _t0) * 1000, True)
        return {"content": [{"type": "text", "text": _json_text(e.payload())}],
                "isError": True}
    except TimeoutError as e:           # legacy ToolDef.timeout (audit A3)
        metrics.record(name, (time.perf_counter() - _t0) * 1000, True)
        err = tool_error("timeout", str(e), retryable=True)
        return {"content": [{"type": "text", "text": _json_text(err.payload())}],
                "isError": True}
    except Exception as e:
        metrics.record(name, (time.perf_counter() - _t0) * 1000, True)
        err = tool_error("internal", str(e), retryable=True)
        return {"content": [{"type": "text", "text": _json_text(err.payload())}],
                "isError": True}
    if d.is_error(res):                 # audit A2: structured app errors
        env = _app_error_envelope(res)
        return {"content": [{"type": "text", "text": _json_text(env)}],
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
