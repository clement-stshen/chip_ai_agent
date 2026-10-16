"""Stage 5: expose the DVCon 2025/2026 paper corpus as FastMCP tools.

Run standalone:
    .venv/bin/python -m chip_ai_agent.fastmcp_dvcon_server
The server speaks MCP over stdio and exposes:
  * search_dvcon_papers(query, year?, kind?, tag?, top_k?) - vector
    retrieval over DVCon US 2025/2026 papers (abstract/method/conclusion)
  * propose_verification_methodology(intent, tag?) - grounded methodology
    proposal citing the top matching papers (stage 6 consumer tool)

Any MCP client (Pydantic AI / Claude Code / Codex / the chip_ai_agent
McpAdapter) can attach to it as a local stdio MCP server.
"""

from __future__ import annotations

from . import dvcon_index

try:                       # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ModuleNotFoundError:  # mcp 2.x: FastMCP renamed to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server

mcp = _Server("dvcon-papers")


@mcp.tool()
def search_dvcon_papers(query: str, year: str | None = None,
                        kind: str | None = None, tag: str | None = None,
                        top_k: int = 5) -> dict:
    """Search DVCon 2025/2026 papers (kind: abstract/method/conclusion)."""
    return dvcon_index.search(query, year=year, kind=kind, tag=tag,
                              top_k=max(1, min(20, top_k)))


@mcp.tool()
def propose_verification_methodology(intent: str, tag: str | None = None,
                                     top_k: int = 4) -> dict:
    """Propose a verification methodology for the given intent, grounded
    with the most relevant DVCon papers as cited evidence."""
    hits = dvcon_index.search(intent, tag=tag,
                              top_k=max(1, min(8, top_k))).get("hits", [])
    citations = [{"title": h["title"], "authors": h["authors"],
                  "year": h["year"], "tags": h.get("tags", []),
                  "excerpt": h.get("excerpt", "")[:300]}
                 for h in hits]
    steps = [
        {"step": "spec_decomposition",
         "how": "拆解 intent 为可验证的 requirement 清单, 建立需求↔测试追溯",
         "evidence": [c["title"] for c in citations
                      if "spec" in c["title"].lower()][:2]},
        {"step": "strategy_selection",
         "how": "按 tag (ai/verification/low-power/cdc/timing/signoff/"
                "stimulus) 选择仿真/形式/混合策略, 引用最相关论文方法",
         "evidence": [c["title"] for c in citations][:3]},
        {"step": "implementation",
         "how": "UVM 环境工厂 + SVA 断言 + 覆盖点落地; 优先复用检索到的 "
                "paper 方法, 不确定处回查 search_dvcon_papers",
         "evidence": []},
        {"step": "closure_and_learning",
         "how": "覆盖率/断言统计回归闭环; 将命中方法写入领域记忆以便下次直接召回",
         "evidence": []},
    ]
    return {"intent": intent, "grounded": bool(citations),
            "citations": citations, "proposed_steps": steps}


if __name__ == "__main__":
    mcp.run()                                   # stdio transport
