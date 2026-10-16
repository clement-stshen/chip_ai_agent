#!/usr/bin/env bash
# Install the official MCP Python SDK v2 into the project venv so that
# mcp_server.py runs in SDK mode (MCPServer). Without it, mcp_server.py
# transparently falls back to the zero-dependency legacy JSON-RPC loop.
#
# Usage:  ./chip_ai_agent/install_sdk.sh [--pypi]
#   default  : build from the local SDK source tree (the analyzed tree)
#   --pypi   : install the released mcp==2.3.0 wheel from PyPI instead
#
# The local source uses dynamic versioning (uv-dynamic-versioning); the
# computed dev version has no matching mcp-types release on PyPI, so the
# version is pinned to 2.3.0 via UV_DYNAMIC_VERSIONING_BYPASS.
set -euo pipefail

SDK_SRC="${CHIP_MCP_SDK_SRC:-/tools/Synopsys/temp/python-sdk}"
VENV_PY="${CHIP_AGENT_PYTHON:-/tools/lsf_api/.venv/bin/python}"
SDK_PIN="2.3.0"

MODE="${1:-local}"
case "$MODE" in
  --pypi)
    "$VENV_PY" -m pip install "mcp==${SDK_PIN}"
    ;;
  local)
    if [ ! -d "$SDK_SRC" ]; then
      echo "error: SDK source tree not found: $SDK_SRC" >&2
      echo "fallback: run with --pypi to install the released wheel" >&2
      exit 1
    fi
    UV_DYNAMIC_VERSIONING_BYPASS="$SDK_PIN" \
      "$VENV_PY" -m pip install "$SDK_SRC"
    ;;
  *)
    echo "usage: $0 [--pypi]" >&2
    exit 2
    ;;
esac

"$VENV_PY" -c "
import mcp
from mcp.server.mcpserver import MCPServer
print(f'MCP SDK {mcp.__version__ if hasattr(mcp, \"__version__\") else \"?\"} OK: {MCPServer.__module__}')
"
