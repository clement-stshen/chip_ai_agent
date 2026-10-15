---
name: vplan_coverage_traceability
description: DVCon 2025-2026 vplan 回链: 验证计划条目 ↔ 测试 ↔ 覆盖数据双向追踪
---
# Verification-Plan to Coverage Traceability

## When To Use
- 验证计划条目需要闭环到覆盖率证据时
- 验签阶段 / 里程碑 review

## Method (DVCon 2025)
1. 每条 vplan 条目登记: 关联 SVA / 测试名 / 目标覆盖点
2. 每次运行落库 (agent runs/steps 表), run_id 即追溯锚点
3. 覆盖数据更新后反向核对: 哪些条目证据缺失
4. 输出条目级状态: closed / evidence_missing / open

## Steps
  1. 报告落库时携带 intent/recipe 作为条目键
  2. runs_using_skill / skill_success_rate 汇总证据
  3. 覆盖洞报告与条目清单做差集

## Pitfalls
- 无 run_id 的手工验证结果不可作为闭环证据
