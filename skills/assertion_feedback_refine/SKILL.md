---
name: assertion_feedback_refine
description: DVCon 2025 断言质量反馈环: 用断言统计驱动 SVA 修订与用例补齐
---
# Assertion Quality Feedback Loop

## When To Use
- 断言通过率虚高 (从未触发) 或误报频繁时

## Method (DVCon 2025)
1. 零命中断言 = 无效断言: 检查前提是否过强, 或场景缺失
2. 高误报断言 = 干扰断言: 加 antecedent/disable iff, 而非删除
3. 每次修订后重新 evaluate, 记录修订前后 hit/fp 变化
4. 修订记录落库, 形成断言版本历史

## Steps
  1. get_assertion_statistics 分桶: 零命中/误报/正常
  2. 零命中 → trace_signal 验证场景是否存在
  3. 误报 → 检查复位期/异步前提
  4. 修订 → evaluate → 对比

## Pitfalls
- 通过率 ≠ 质量, 看命中分布; 全部通过且全部零命中是典型假绿
