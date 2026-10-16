"""Stage 5: wrap the PCIe OVM guide corpus as FastMCP tools.

Run standalone:
    .venv/bin/python -m chip_ai_agent.fastmcp_pcie_server
The server speaks MCP over stdio and exposes:
  * search_pcie_guide(query, kind?, top_k?)  - vector retrieval over the
    Synopsys PCIe OVM User Guide structured units
  * generate_pcie_config(device, spec_ver?, link_width?, speed?) -
    emits a parameterized OVM configuration class (stage 6 consumer tool),
    grounded with the top retrieved guide sections

Any MCP client (Pydantic AI / Claude Code / Codex / the chip_ai_agent
McpAdapter) can attach to it as a local stdio MCP server (stage 6).
"""

from __future__ import annotations

from . import pcie_index

try:                       # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ModuleNotFoundError:  # mcp 2.x: FastMCP renamed to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server

mcp = _Server("pcie-ovm-guide")

_SPEED = {
    "2.5": "SVT_PCIE_SPEED_2_5_G",
    "5": "SVT_PCIE_SPEED_5_G",
    "8": "SVT_PCIE_SPEED_8_G",
    "16": "SVT_PCIE_SPEED_16_G",
    "32": "SVT_PCIE_SPEED_32_G",
}


@mcp.tool()
def search_pcie_guide(query: str, kind: str | None = None,
                      top_k: int = 5) -> dict:
    """Search the Synopsys PCIe OVM User Guide corpus (kind: steps/code/prose)."""
    return pcie_index.search(query, top_k=max(1, min(10, top_k)), kind=kind)


@mcp.tool()
def generate_pcie_config(device: str = "root", spec_ver: str = "2.1",
                         link_width: int = 1,
                         speed: str = "2.5") -> dict:
    """Generate a PCIe OVM configuration class for the requested topology,
    grounded with the most relevant User Guide sections."""
    speed_tok = _SPEED.get(speed.replace("GT/s", "").strip(), _SPEED["2.5"])
    spec_tok = f"PCIE_SPEC_VER_{spec_ver.replace('.', '_')}"
    grounding = pcie_index.search(
        "configuration device root link width target speed", top_k=3)
    code = f"""class pcie_shared_cfg extends ovm_object;
  rand svt_pcie_device_configuration root_cfg;

  function new(string name = "pcie_shared_cfg");
    super.new(name);
    this.root_cfg = new("pcie_shared_cfg");
    root_cfg.device_is_root = {1 if device == "root" else 0};
    root_cfg.pcie_spec_ver = svt_pcie_device_configuration::{spec_tok};
    root_cfg.pcie_cfg.pl_cfg.link_width = {int(link_width)};
    root_cfg.pcie_cfg.pl_cfg.target_speed = {speed_tok};
    root_cfg.pcie_cfg.pl_cfg.skip_polling_active = 1;
  endfunction : new
endclass : pcie_shared_cfg"""
    return {"config_code": code,
            "grounding": [{"section": h["section"], "chapter": h["chapter"],
                           "score": h["score"]}
                          for h in grounding.get("hits", [])]}


if __name__ == "__main__":
    mcp.run()                                   # stdio transport
