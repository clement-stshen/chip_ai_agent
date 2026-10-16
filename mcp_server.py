#!/usr/bin/env python3
"""Chip AI Agent MCP server — dual-mode entry point.

Primary (SDK mode):  built on the official MCP Python SDK v2 (MCPServer) —
typed input validation, tool annotations, progress reporting, resources,
prompts, and optional streamable-HTTP transport.

Fallback (legacy mode): zero-dependency stdio JSON-RPC loop over the SAME
tool surface (mcp_tools.TOOL_DEFS) — used automatically when the SDK is not
importable, or forced with CHIP_AGENT_MODE=legacy.

Run (from anywhere):
    "$CHIP_AGENT_PYTHON" "$CHIP_AGENT_HOME/mcp_server.py"
    (defaults: python3, package directory; see INTEGRATION.md for env list)

Environment:
    CHIP_AGENT_MODE        auto (default) | sdk | legacy
    CHIP_AGENT_TRANSPORT   stdio (default) | streamable-http
    CHIP_AGENT_HOST/PORT   HTTP bind (default 127.0.0.1:8000)
    CHIP_AGENT_SKILLS / CHIP_AGENT_EXTRA_SKILLS / CHIP_AGENT_DB /
    CHIP_AGENT_EXPERIENCE  (see INTEGRATION.md)

Register:
    claude mcp add chip-agent -s user -- "$CHIP_AGENT_PYTHON" "$CHIP_AGENT_HOME/mcp_server.py"
    # codex: ~/.codex/config.toml [mcp_servers.chip_agent]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# allow running as a script from any cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROTOCOL = "2024-11-05"


# ---------------------------------------------------------------------------
# legacy mode: zero-dependency stdio JSON-RPC loop (SDK absent / forced)
# ---------------------------------------------------------------------------

def _legacy_handle(msg: dict) -> dict | None:
    from chip_ai_agent.mcp_tools import (SERVER_NAME, SERVER_VERSION,
                                         call_tool, tools_schema)
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {}) or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": params.get("protocolVersion", PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        # optional server-side filter: tools/list {"domain": "verification"}
        # unknown domain → explicit empty list (client-visible contract)
        domain = params.get("domain") if isinstance(params, dict) else None
        return {"jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": tools_schema(domain)}}
    if method == "tools/call":
        res = call_tool(params.get("name", ""), params.get("arguments", {}) or {})
        return {"jsonrpc": "2.0", "id": msg_id, "result": res}
    if msg_id is not None:
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def _legacy_main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _legacy_handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# SDK mode: official MCP Python SDK v2 (MCPServer)
# ---------------------------------------------------------------------------

def _sdk_main() -> int:
    from chip_ai_agent.mcp_tools import build_sdk_server, transport_config
    srv = build_sdk_server()
    transport, kwargs = transport_config()
    if transport == "stdio":
        srv.run(transport="stdio")
    else:
        srv.run(transport="streamable-http", **kwargs)
    return 0


def main() -> int:
    mode = os.environ.get("CHIP_AGENT_MODE", "auto")
    if mode == "legacy":
        return _legacy_main()
    if mode == "sdk":
        return _sdk_main()
    try:
        import mcp  # noqa: F401
    except ImportError:
        return _legacy_main()
    return _sdk_main()


if __name__ == "__main__":
    sys.exit(main())
