---
name: formal_failure_debug
description: >
  DVCon 2026 最佳论文 FVDebug 方法论: 形式化验证失败根因分析四段流水线 —
  因果图合成(信号事件 DAG) → 图扫描器(for-and-against 正反论证消偏) →
  Insight Rover(agentic 假设排序) → Fix Generator(RTL patch)。
  实证数据: SVA-Eval-Human 71.1% Pass@1 / 86.8% Pass@5; 显式因果边是
  准确根因识别的基础 (Flat Trace 基线 Quality@Best 仅 0.474 vs 0.956)。
version: 1.0.0
---
# Formal Failure Debug (FVDebug 四段流水线, 可直接复用)

## When To Use
- formal / FPV 反例(CEX)分析、断言失败根因定位
- intent 匹配 "counterexample / 反例分析 / 根因定位 / fv debug" → fv_failure_debug recipe
- 多周期反例人工回溯耗时数小时以上的场景

## Method — 四段流水线 (DVCon 2026 NVIDIA FVDebug)

1. **因果图合成**: 平铺反例轨迹 → 信号事件 DAG (节点 signal@cycle=value,
   边=直接因果依赖)。本技能面等价链: evaluate_assertion 取失败断言与时间点 →
   find_signal_transition_to_value / detect_unknown_and_get_previous_or_next_transitions
   沿信号依赖回溯 (因果边)。
2. **图扫描器**: 对可疑节点做批量 LLM 分析, **for-and-against 正反论证**
   (同时论证"该节点是根因"与"该节点不是根因", 消确认偏误)。对应
   agentic_debug_workflow 的 plan-critique-retry。
3. **Insight Rover**: 以可疑节点为种子做 agentic 假设探索——生成、细化、
   排序多个竞争因果假设并打置信度 (消融实证: 移除后质量 0.956→0.795)。
4. **Fix Generator**: 输出含排序假设 + 因果时间线 + diff 级 RTL patch 的
   报告; 用 sva_assertion_generation 生成修复性断言回验。

## Pitfalls
- 不要平铺分析反例 (Flat Trace 基线质量仅 0.474 — 显式因果边是根本)。
- 单一方向论证有确认偏误: 正反论证提升排序一致性 (Kendall's τ 0.708 vs 0.634)。
- 生产级设计 (多模块/50万+行) 根因链可达 15 层 — 回溯深度要够。
- 修复建议必须可映射回真实 RTL (论文明确: "generated fixes are applicable
  to the actual RTL" 是关键挑战)。
