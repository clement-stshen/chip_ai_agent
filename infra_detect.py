"""Infrastructure tool detection aligned with the vendored infrastructure
skill: 24 open-source tools (PATH + common roots) and 7 proprietary tools
(detect only — never install). Emits per-tool setup guidance and the
wrapper/MCP deployment state.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .eda_wrappers import WRAPPERS_DIR

OSS_TOOLS = [
    "verilator", "slang", "surelog", "sv2v", "iverilog", "yosys", "abc",
    "openroad", "openlane", "klayout", "sta", "sby", "gem5", "bambu-hls",
    "nextpnr-xilinx", "openFPGALoader", "cocotb", "llvm-config", "gcc",
    "openocd", "xschem", "gtkwave", "uv", "python3",
]
PROPRIETARY = [
    ("vcs", ["vcs"]), ("xcelium", ["xrun", "xmsim"]),
    ("design-compiler", ["dc_shell", "dc_shell-t"]),
    ("innovus", ["innovus"]), ("questa", ["vsim", "questa", "questasim"]),
    ("primetime", ["pt_shell", "pt_shell64"]),
    ("formality", ["formality", "fm_shell"]),
]


def detect_tools() -> dict:
    oss = {}
    for t in OSS_TOOLS:
        path = shutil.which(t)
        oss[t] = {"available": path is not None, "path": path,
                  "setup": None if path else f"install or load module providing '{t}'"}
    prop = {}
    for name, binaries in PROPRIETARY:
        hit = next((b for b in binaries if shutil.which(b)), None)
        prop[name] = {
            "available": hit is not None, "binary": hit,
            "policy": "detect-only (never auto-install)",
            "setup": None if hit else "module load vendor toolkit",
        }
    wrappers = sorted(WRAPPERS_DIR.glob("wrap-*.sh"))
    mcp_configs = sorted((WRAPPERS_DIR.parent / "mcp").glob("mcp-*.json"))
    return {
        "open_source": {k: v for k, v in oss.items() if v["available"]},
        "open_source_missing": [k for k, v in oss.items() if not v["available"]],
        "proprietary": {k: v for k, v in prop.items() if v["available"]},
        "proprietary_missing": [k for k, v in prop.items() if not v["available"]],
        "wrappers": {"total": len(wrappers),
                     "executable": sum(1 for w in wrappers
                                       if w.stat().st_mode & 0o111),
                     "dir": str(WRAPPERS_DIR)},
        "mcp_configs": {"total": len(mcp_configs),
                        "dir": str(WRAPPERS_DIR.parent / "mcp")},
        "summary": (
            f"oss={sum(v['available'] for v in oss.values())}/{len(oss)} "
            f"prop={sum(v['available'] for v in prop.values())}/{len(prop)} "
            f"wrappers={sum(1 for w in wrappers if w.stat().st_mode & 0o111)}"
            f"/{len(wrappers)} mcp={len(mcp_configs)}"),
    }
