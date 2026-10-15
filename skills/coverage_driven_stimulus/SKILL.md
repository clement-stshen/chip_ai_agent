---
name: coverage_driven_stimulus
description: DVCon 2025 覆盖率驱动智能激励: 从覆盖洞回溯 RTL 条件并推导针对性 stimulus
---
# Coverage-Driven Intelligent Stimulus

## When To Use
- 覆盖率有洞且常规随机激励长时间无法命中时
- coverage_driven_stimulus recipe 的执行阶段

## Method (DVCon 2025)
1. 定位覆盖洞 → 对应表达式/分支 → RTL 条件
2. 分析该条件的历史取值分布 (波形取证), 判断"不可达/欠激励/约束冲突"
3. 只对"欠激励"类生成针对性 stimulus; 不可达洞应报告而非硬凑
4. 生成的 stimulus 必须先 trace_signal 验证可驱动到目标信号

## Steps
  1. get_coverage_summary / get_uncovered_expressions 定位洞
  2. get_source_code 回溯条件上下文
  3. 用信号事件报告判断欠激励原因
  4. 输出针对性 stimulus 建议 (含约束修改点)

## Pitfalls
- 不可达代码导致的覆盖洞不应消耗激励迭代预算, 先分类再动手
