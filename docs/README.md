# 芯片研发与验证智能 AI Agent

## 1. 能力面概述

**126 个技能目录**(92 顶层 + `waveform/` 3 + `design_exploration/` 33),
全部自包含于 `chip_ai_agent/skills/`,覆盖 7 大域:设计探索、调试追踪
(驱动链/X 传播)、波形取证(FSDB)、断言、覆盖率收敛、功耗/UPF、源码检索。

## 2. 芯片研发与验证痛点(由该能力面反推)

1. **海量层级/信号检索慢** → 需要 hierarchical grep + "who drives X" 语义追问
2. **X 传播/未初始化 bug 定位难**,驱动链横跨 RTL 与波形 → trace_x 自动回溯
3. **断言失败分诊耗时**,失败现场分散在时间点/波形/源码 → 一键现场取证
4. **覆盖率收敛靠人工逐条判断** → 批量高亮 + 豁免辅助
5. **UPF/功耗问题隐蔽**,电源域关系复杂 → 关系图 + 时点状态核对
6. **新设计上手成本高** → 架构解释、微架构识别、接口协议发现自动化
7. **调试知识未沉淀** → Agent 输出结构化 RunReport,可入库复用

## 3. 架构

```
intent ─▶ Planner(recipes.py 意图匹配)
            │
            ▼
     Workflow(有序技能链)
            │
            ▼
   SkillRegistry(skills/ 扫描,识别加密/明文)
            │
            ▼
   McpAdapter(stdio JSON-RPC tools/call → Synopsys MCP server)
            │
            ▼
      RunReport(步骤 + 证据,可归档)
```

## 4. 使用


python3 -m chip_ai_agent.cli "trace X propagation of u_core/dout" \
    --server <verdi-mcp-server-cmd> --args...


