"""Central site-path configuration.

Every absolute path that used to be hardcoded across modules lives here,
each overridable by an environment variable (read at import time, matching
the SKILLS_DIR convention). Defaults preserve the current site layout so a
zero-config deployment behaves exactly as before; set the variables to
relocate to another EDA site or a different project root.

Env variables:
  CHIP_AGENT_TEMPLATE_TB        UVM testbench template project
  CHIP_AGENT_MODULEFILES        ':'-separated modulefile paths
  CHIP_AGENT_EDA_ROOTS          ':'-separated EDA vendor search roots
  CHIP_AGENT_NPI_ROOT           NPI kit (pynpi + lib + inc)
  CHIP_AGENT_UVM_ROOT           Accellera UVM reference library dir
  CHIP_AGENT_UVM_TGZ_ROOT       dir holding the uvm-1.x tarballs (parent)
  CHIP_AGENT_UG_ROOT            UG manual corpus root (ug_index)
  CHIP_AGENT_DVCON_ROOT         DVCon corpus root (dvcon_index)
  CHIP_AGENT_EXAMPLE_UART       Verification Academy UART example tree
  CHIP_AGENT_VERIF_AGENT_BIN    verif-agent-mcp executable
  CHIP_AGENT_VERIF_AGENT_CONFIG verif-agent-mcp config.yaml
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_list(name: str, default: str) -> list[str]:
    return [p for p in _env(name, default).split(":") if p]


# -- project template ---------------------------------------------------------
TEMPLATE_TB = Path(_env("CHIP_AGENT_TEMPLATE_TB", "/tools/lsf_api/uvm_tb"))

# -- EDA site discovery --------------------------------------------------------
MODULEFILES = _env_list(
    "CHIP_AGENT_MODULEFILES",
    "/usr/share/Modules/modulefiles/synopsys:/tools/Synopsys/scl/modulefile")
COMMON_ROOTS = _env_list(
    "CHIP_AGENT_EDA_ROOTS", "/tools/Synopsys:/eda/synopsys:/opt/synopsys")

# -- NPI kit (pynpi execution layer) -------------------------------------------
NPI_ROOT = Path(_env("CHIP_AGENT_NPI_ROOT", "/tools/Synopsys/temp/NPI"))
NPI_PY = NPI_ROOT / "python"
NPI_LIB = NPI_ROOT / "lib" / "linux64"
NPI_INC = NPI_ROOT / "inc"

# -- Accellera UVM reference library -------------------------------------------
UVM_ROOT = Path(_env("CHIP_AGENT_UVM_ROOT", "/tools/Synopsys/temp/uvm"))
UVM_TGZ_ROOT = Path(_env("CHIP_AGENT_UVM_TGZ_ROOT", "/tools/Synopsys/temp"))

# -- corpus roots ---------------------------------------------------------------
UG_ROOT = Path(_env("CHIP_AGENT_UG_ROOT", "/tools/Synopsys/temp/ug"))
DVCON_ROOT = Path(_env(
    "CHIP_AGENT_DVCON_ROOT", str(Path(__file__).parent / "dvcon")))

# -- example tree ---------------------------------------------------------------
UART_EXAMPLE = Path(_env("CHIP_AGENT_EXAMPLE_UART",
                         "/tools/Synopsys/temp/uart_example"))

# -- Synopsys verif-agent-mcp ---------------------------------------------------
VERIF_AGENT_BIN = Path(_env(
    "CHIP_AGENT_VERIF_AGENT_BIN",
    "/opt/verif-agent-mcp/venv/bin/verif-agent-mcp"))
VERIF_AGENT_CONFIG = Path(_env(
    "CHIP_AGENT_VERIF_AGENT_CONFIG", "/etc/verif-agent-mcp/config.yaml"))
