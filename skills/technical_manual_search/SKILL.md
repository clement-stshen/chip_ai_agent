---
name: technical_manual_search
description: 技术手册全文检索与语料管线 (VCS/Verdi/UVM/ChipStack 127 册): 章节/操作步骤/flow/示例 6 类切分单元, 哈希 TF-IDF 向量索引, SFT 语料生成
---
# Technical Manual Corpus Skill

## When To Use
- 查询 VCS 编译选项、仿真 flow、覆盖率方法、debug 技巧 (引用原文章节)
- 查询 Verdi 波形操作、nWave/NPI 命令、UVM debug、功耗分析流程
- 查询 UVM 方法学章节 (phase/objection/factory/config_db/sequence-sequencer)
- 查询 ChipStack Agent 配置、CLI/TUI/WebUI 用法、工作流定义
- 需要精确的命令行示例或操作步骤时 (kind=steps/example)
- 需要理解完整 flow 的阶段/产物/handoff 时 (kind=flow)

## Data Assets (已构建)

| 阶段 | 产物 | 路径 |
|---|---|---|
| ① 扫描+分类 | 131 候选 → 127 技术手册 (4 拒绝: 2 HTML app shell + 2 空短 PDF) | `corpus/technical_manuals/inventory.json` |
| ② 提取 | 127 册文本缓存 (复用 UG 旁侧 .txt.gz) | `corpus/technical_manuals/extracted/` |
| ③ 结构化切分 | **211,835 单元** (chapter 1434 / section 27821 / steps 76 / flow 4149 / example 3948 / prose 174407) | `corpus/technical_manuals/structured_units.jsonl` |
| ④ 模型语料 | 211,835 条 Alpaca SFT (6 类 instruction 模板) | `corpus/technical_manuals/model_sft.jsonl` |
| ⑤ 向量索引 | hashed TF-IDF (dim 2^18, 倒排加速) | `corpus/technical_manuals/manual_vectors.npz` |

### 按产品分布
- **VCS**: 76 册 (cmd_ref / user_guide / coverage / ICO / SVA / UVM / VMM / LCA …)
- **Verdi**: 50 册 (command_ref / tutorial / UVM_debug / NPI / coverage / power_aware / TCL …)
- **ChipStack**: 1 册 (ChipStack User Guide 2.0 — Cadence agentic verification platform)

### 切分单元 kind 语义
| kind | 含义 | 典型用途 |
|---|---|---|
| chapter | 章级标题锚点 | 定位手册结构、概览 |
| section | 节级上下文 (标题+首段) | 概念解释、配置说明 |
| steps | 操作步骤序列 (1. 2. 3.…) | 精确复现操作 |
| flow | 多阶段流程 (含 stage/phase/arrow) | 理解 handoff 与产物 |
| example | 代码/命令行示例块 | 复制可用命令 |
| prose | 正文上下文 | 自由问答 |

## Method

### MCP 工具 (推荐)
1. **chip_manual_search** — 检索
   ```
   chip_manual_search(query="VCS two-step compile flow", kind="flow", top_k=5)
   chip_manual_search(query="Verdi nWave signal search", product="verdi", kind="steps")
   chip_manual_search(query="coverage merge report", product="vcs", kind="example")
   ```
2. **chip_manual_ingest** — 管线
   ```
   chip_manual_ingest(op="status")   # 查看当前语料状态
   chip_manual_ingest(op="build")    # 全量重建 (新手册放入扫描根后)
   chip_manual_ingest(op="scan")     # 仅扫描候选
   ```

### 进程内检索
```python
from chip_ai_agent import manual_ingest
manual_ingest.search("UVM factory override", kind="section", top_k=3)
```

### CLI
```bash
python -m chip_ai_agent.manual_ingest search "low power UPF simulation" --product vcs --kind flow
python -m chip_ai_agent.manual_ingest status
```

## Pitfalls
- 未 build 时 `search` 返回 error: 先跑 `chip_manual_ingest(op="build")` 或 `python -m chip_ai_agent.manual_ingest build`
- `kind=steps` 命中较少 (76 条): 许多手册的步骤被识别为 `example` 或 `prose`; 优先用 `kind=flow` 或不限 kind
- `product` 过滤区分大小写: 用小写 `vcs`/`verdi`/`chipstack`
- 原文片段默认截断 4000 字符: 增大 `max_text` 参数或直接读 `structured_units.jsonl` 获取全文
- SFT 语料的 instruction 是启发式模板生成: 精调前需人工审校 quality
