#!/usr/bin/env bash
# Offline install: all wheels ship with the package in chip_ai_agent/wheelhouse
# (mcp 2.3.0 + mcp-types + numpy + pypdf + pytest + lxml + matplotlib
#  and full transitive closure).
# Verified: a bare venv + --no-index --find-links installs and imports MCPServer.
set -euo pipefail

if [ -n "${CHIP_AGENT_WHEELHOUSE:-}" ]; then
    WHEELHOUSE="$CHIP_AGENT_WHEELHOUSE"
else
    WHEELHOUSE="$(cd "$(dirname "$0")" && pwd)/wheelhouse"
fi
if [ -n "${CHIP_AGENT_PYTHON:-}" ]; then
    VENV_PY="$CHIP_AGENT_PYTHON"
elif [ -x "$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python" ]; then
    VENV_PY="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
else
    VENV_PY="python3"
fi

"$VENV_PY" -m pip install --no-index --find-links "$WHEELHOUSE" \
    "mcp==2.3.0" "mcp-types==2.3.0" numpy pypdf pytest \
    beautifulsoup4 fonttools lxml matplotlib

"$VENV_PY" -c "
from mcp.server.mcpserver import MCPServer
import numpy, pypdf
print('offline deps OK:', MCPServer.__module__)
"
