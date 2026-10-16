#!/usr/bin/env bash
# Offline install: all wheels are pre-downloaded in /tools/lsf_api/wheelhouse
# (mcp 2.3.0 + mcp-types + numpy + pypdf + pytest and full transitive closure).
# Verified: a bare venv + --no-index --find-links installs and imports MCPServer.
set -euo pipefail

WHEELHOUSE="${CHIP_AGENT_WHEELHOUSE:-/tools/lsf_api/wheelhouse}"
VENV_PY="${CHIP_AGENT_PYTHON:-/tools/lsf_api/.venv/bin/python}"

"$VENV_PY" -m pip install --no-index --find-links "$WHEELHOUSE" \
    "mcp==2.3.0" "mcp-types==2.3.0" numpy pypdf pytest \
    beautifulsoup4 fonttools

"$VENV_PY" -c "
from mcp.server.mcpserver import MCPServer
import numpy, pypdf
print('offline deps OK:', MCPServer.__module__)
"
