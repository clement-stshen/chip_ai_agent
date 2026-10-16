---
name: dvcon_papers
description: DVCon US 2025/2026 论文领域技能: 137 篇官方论文向量检索 + SFT 语料 + 方法论提案, 支持 FastMCP 工具接入
---
# DVCon Papers Skill (conference-corpus → agent-skill chain)

## When To Use
- 为验证意图选择方法论: formal/UVM/低功耗/CDC/约束/signoff/portable stimulus
- 引用真实 DVCon 论文作为方法依据 (title/authors/year/tags 可溯源)
- 需要 SFT 语料做领域微调, 或通过 MCP 把论文检索接入任意 agent 客户端

## Data Assets (已构建)
| 资产 | 内容 | 路径 |
|---|---|---|
| 种子库 | 137 篇 (2025×73 / 2026×64), 官方技术程序解析 | `dvcon_seed_corpus.json` |
| 向量索引 | hashed tf-idf, 144 chunks (abstract 137 / method 7) | `dvcon/dvcon_vectors.npz` |
| 主动记忆 | 按 track tag 蒸馏的 dvcon_knowledge.md | `dvcon/dvcon_knowledge.md` |
| SFT 语料 | curated 3 + seed 137 + unit 1 = 141 条 Alpaca | `corpus/dvcon/dvcon_sft.jsonl` |

## Method
1. 进程内检索: `python -m chip_ai_agent.dvcon_index search '<q>' [--year --kind --tag]`
2. 本地 FastMCP 工具 (推荐): 启动
   `.venv/bin/python -m chip_ai_agent.fastmcp_dvcon_server`
   暴露 `search_dvcon_papers` 与 `propose_verification_methodology` 两个 MCP tool
3. Agent 接入: 把该命令注册为 stdio MCP server; 任何 MCP 客户端
   (Pydantic AI / Claude Code / Codex / chip_ai_agent McpAdapter) 均可调用
4. 引用规范: 方法论建议必须附带 `citations` (title/authors/year);
   未检索到依据时如实返回 `grounded: false`, 不得编造论文
5. 语料更新: 替换 seed JSON 或在 `dvcon/` 放入全文 .md/.txt/.pdf 后, 依次跑
   `digest → build → sft` 三个子命令

## Pitfalls
- 未 build 时检索返回 error: 先跑 `python -m chip_ai_agent.dvcon_index build`
- `propose_verification_methodology` 是模板级提案, 论文出处真实但步骤需按项目裁剪
- tag 仅 7 类 (ai/verification/low-power/cdc/timing/signoff/stimulus),
  由 title+summary 关键词自动标注
