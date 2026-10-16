---
name: pcie_ovm_guide
description: PCIe OVM VIP 领域技能: 用户手册向量检索 + 配置代码生成, 支持本地 FastMCP 工具接入
---
# PCIe OVM Guide Skill (manual → agent-skill chain)

## When To Use
- 生成/检查 PCIe OVM VIP 的 testbench 配置 (root/endpoint, spec, link width, speed)
- 回答 PCIe VIP 使用问题: 复位序列 / 覆盖率回调 / TLP-DLLP / LTSSM / credit 初始化
- 需要引用 User Guide 原文章节作为依据时

## Data Assets (已构建)
| 阶段 | 产物 | 路径 |
|---|---|---|
| ① 提取+切分 | 115 结构化单元 (chapter/steps/code/prose) | `corpus/pcie_ovm/ug/structured_units.jsonl` |
| ① 向量索引 | hashed tf-idf (复用 ug_index, dim 2^18) | `corpus/pcie_ovm/ug/pcie_vectors.npz` |
| ② SFT 语料 | curated 23 + generated 67 = 90 条 Alpaca | `corpus/pcie_ovm/pcie_ovm_sft.jsonl` |

## Method
1. 进程内检索: `python -c "from chip_ai_agent import pcie_index; print(pcie_index.search('<q>', kind='steps'))"`
2. 本地 FastMCP 工具 (推荐, 阶段⑤): 启动
   `.venv/bin/python -m chip_ai_agent.fastmcp_pcie_server`
   暴露 `search_pcie_guide` 与 `generate_pcie_config` 两个 MCP tool
3. Agent 接入 (阶段⑥): 把该命令注册为 stdio MCP server; 任何 MCP 客户端
   (Pydantic AI / Claude Code / Codex / chip_ai_agent McpAdapter) 均可调用
4. 引用规范: 回答 PCIe VIP 问题时优先引用 `chapter/section` 字段,
   代码示例必须来自 `kind=code` 单元或 `generate_pcie_config` 输出

## Pitfalls
- 未 build 时 `search` 返回 error: 先跑 `python -m chip_ai_agent.pcie_index build`
- `generate_pcie_config` 是模板级输出 (静态正确), 不替代 UG 中 per-port 的高级配置
- LoRA 微调后 (阶段③④) 模型仅是加速器, 事实性来源仍以本技能的检索结果为准
