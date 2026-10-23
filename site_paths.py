"""Central site-path configuration (layered, zero hardcoded site paths).

Resolution order for every key:

1. process environment variable (highest priority)
2. JSON config file: ``$CHIP_AGENT_CONFIG`` or, when unset,
   ``<package>/site_config.json`` when present (site overlay, not code)
3. portable in-package default derived from ``__file__`` (never a site
   literal; absent paths degrade gracefully with setup guidance)

Config-file keys use exactly the same names as the environment variables,
so an operator can lift any deployment from ``site_config.example.json``
and override a single key with an env var without editing code.

Env/config keys:
  CHIP_AGENT_CONFIG               path to the JSON site config itself
  CHIP_AGENT_TEMPLATE_TB          UVM testbench template project
  CHIP_AGENT_MODULEFILES          ':'-separated modulefile paths
  CHIP_AGENT_EDA_ROOTS            ':'-separated EDA vendor search roots
  CHIP_AGENT_NPI_ROOT             NPI kit (pynpi + lib + inc)
  CHIP_AGENT_UVM_ROOT             Accellera UVM reference library dir
  CHIP_AGENT_UVM_TGZ_ROOT         dir holding the uvm-1.x tarballs (parent)
  CHIP_AGENT_UG_ROOT              UG manual corpus root (ug_index)
  CHIP_AGENT_DVCON_ROOT           DVCon corpus root (dvcon_index)
  CHIP_AGENT_UVM_SRC_ROOT         UVM 1.2 source KB root
  CHIP_AGENT_EXAMPLE_UART         Verification Academy UART example tree
  CHIP_AGENT_EXAMPLES             examples corpus root (examples_index)
  CHIP_AGENT_VERIF_AGENT_BIN      verif-agent-mcp executable
  CHIP_AGENT_VERIF_AGENT_CONFIG   verif-agent-mcp config.yaml
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_PKG_PARENT = _PKG.parent

_CONFIG_PATH = Path(os.environ.get("CHIP_AGENT_CONFIG", str(_PKG / "site_config.json")))
try:
    _CONFIG: dict = json.loads(_CONFIG_PATH.read_text(encoding="utf-8")) \
        if _CONFIG_PATH.exists() else {}
except (OSError, ValueError):
    _CONFIG = {}


def _get(name: str, default: str) -> str:
    """env > site_config.json > portable default."""
    if name in os.environ:
        return os.environ[name]
    if name in _CONFIG:
        return str(_CONFIG[name])
    return default


def _get_list(name: str, default: str) -> list[str]:
    return [p for p in _get(name, default).split(":") if p]


# -- project template ---------------------------------------------------------
TEMPLATE_TB = Path(_get("CHIP_AGENT_TEMPLATE_TB",
                        str(_PKG_PARENT / "uvm_tb")))

# -- EDA site discovery --------------------------------------------------------
MODULEFILES = _get_list("CHIP_AGENT_MODULEFILES", "")
COMMON_ROOTS = _get_list("CHIP_AGENT_EDA_ROOTS", "")

# -- NPI kit (pynpi execution layer) -------------------------------------------
NPI_ROOT = Path(_get("CHIP_AGENT_NPI_ROOT", str(_PKG / "corpus" / "npi")))
NPI_PY = NPI_ROOT / "python"
NPI_LIB = NPI_ROOT / "lib" / "linux64"
NPI_INC = NPI_ROOT / "inc"

# -- Accellera UVM reference library -------------------------------------------
UVM_ROOT = Path(_get("CHIP_AGENT_UVM_ROOT", str(_PKG / "corpus" / "uvm")))
UVM_TGZ_ROOT = Path(_get("CHIP_AGENT_UVM_TGZ_ROOT", str(_PKG / "corpus")))

# -- corpus roots (in-package by default; corpus ships with the agent) ----------
UG_ROOT = Path(_get("CHIP_AGENT_UG_ROOT", str(_PKG / "corpus" / "ug")))
DVCON_ROOT = Path(_get("CHIP_AGENT_DVCON_ROOT", str(_PKG / "dvcon")))
UVM_SRC_ROOT = Path(_get("CHIP_AGENT_UVM_SRC_ROOT", str(_PKG / "uvm_src_kb")))

# -- example tree (golden UART TB vendored in-package) ---------------------------
UART_EXAMPLE = Path(_get("CHIP_AGENT_EXAMPLE_UART",
                         str(_PKG / "corpus" / "uart_example")))

# -- Synopsys verif-agent-mcp ---------------------------------------------------
VERIF_AGENT_BIN = Path(_get(
    "CHIP_AGENT_VERIF_AGENT_BIN", str(_PKG / "bin" / "verif-agent-mcp")))
VERIF_AGENT_CONFIG = Path(_get(
    "CHIP_AGENT_VERIF_AGENT_CONFIG",
    str(_PKG / "config" / "verif-agent-mcp.yaml")))



# -- EDA tool homes (from modulefile or site config) -------------------------
VCS_HOME = Path(_get("VCS_HOME", ""))
VERDI_HOME = Path(_get("VERDI_HOME", ""))
UVM_VERSION = _get("UVM_VERSION", "uvm-1.2")

# -- workflow paths ----------------------------------------------------------
CHIP_AGENT_WORK_ROOT = Path(_get(
    "CHIP_AGENT_WORK_ROOT", str(_PKG_PARENT / "uvm_tb")))
LIVE_LOG = _get("CHIP_AGENT_LIVE_LOG", "/tmp/chip_agent_live.log")

def vcs_bin() -> str:
    """Return VCS binary path (respects VCS_HOME)."""
    vcs = VCS_HOME / "bin" / "vcs"
    return str(vcs) if vcs.exists() else "vcs"

def verdi_bin() -> str:
    """Return Verdi binary path (respects VERDI_HOME)."""
    verdi = VERDI_HOME / "bin" / "verdi"
    return str(verdi) if verdi.exists() else "verdi"

def simv_path(work_dir: Path | None = None) -> str:
    d = work_dir or CHIP_AGENT_WORK_ROOT / "sim"
    return str(d / "simv")

def uvm_home(version: str | None = None) -> str:
    """Return UVM_HOME for the specified (or default) version."""
    v = version or UVM_VERSION
    # Try UVM_ROOT first, then fallback from config
    fallback = Path(str(_CONFIG.get("UVM_FALLBACK", ""))) if _CONFIG.get("UVM_FALLBACK") else UVM_ROOT
    for base in (UVM_ROOT, fallback):
        candidate = base / v
        if (candidate / "src" / "uvm_pkg.sv").exists():
            return str(candidate)
    return str(UVM_ROOT / v)

def eda_env() -> dict:
    """Return env dict for VCS/Verdi subprocess execution."""
    env = os.environ.copy()
    vcs = str(VCS_HOME)
    verdi = str(VERDI_HOME)
    if vcs:
        env["VCS_HOME"] = vcs
        env["PATH"] = f"{vcs}/bin:{vcs}/linux64/bin:" + env.get("PATH","")
    if verdi:
        env["VERDI_HOME"] = verdi
        env["PATH"] = f"{verdi}/bin:{verdi}/platform/LINUX64/bin:" + env.get("PATH","")
        env["LD_LIBRARY_PATH"] = f"{verdi}/share/PLI/VCS/LINUX64:" + env.get("LD_LIBRARY_PATH","")
    env.setdefault("SNPSLMD_LICENSE_FILE", "27080@ipasrv")
    env["UVM_HOME"] = uvm_home()
    return env



def describe_config() -> dict:
    """Effective configuration snapshot for diagnostics/health checks."""
    return {
        "config_path": str(_CONFIG_PATH),
        "config_loaded": bool(_CONFIG),
        "config_keys": sorted(_CONFIG),
        "effective": {
            "CHIP_AGENT_TEMPLATE_TB": str(TEMPLATE_TB),
            "CHIP_AGENT_MODULEFILES": MODULEFILES,
            "CHIP_AGENT_EDA_ROOTS": COMMON_ROOTS,
            "CHIP_AGENT_NPI_ROOT": str(NPI_ROOT),
            "CHIP_AGENT_UVM_ROOT": str(UVM_ROOT),
            "CHIP_AGENT_UVM_TGZ_ROOT": str(UVM_TGZ_ROOT),
            "CHIP_AGENT_UG_ROOT": str(UG_ROOT),
            "CHIP_AGENT_DVCON_ROOT": str(DVCON_ROOT),
            "CHIP_AGENT_UVM_SRC_ROOT": str(UVM_SRC_ROOT),
            "CHIP_AGENT_EXAMPLE_UART": str(UART_EXAMPLE),
            "CHIP_AGENT_VERIF_AGENT_BIN": str(VERIF_AGENT_BIN),
            "CHIP_AGENT_VERIF_AGENT_CONFIG": str(VERIF_AGENT_CONFIG),
            "VCS_HOME": str(VCS_HOME),
            "VERDI_HOME": str(VERDI_HOME),
            "UVM_VERSION": UVM_VERSION,
            "CHIP_AGENT_WORK_ROOT": str(CHIP_AGENT_WORK_ROOT),
            "CHIP_AGENT_LIVE_LOG": LIVE_LOG,
        },
    }
