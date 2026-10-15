---
name: agentic_debug_workflow
description: DVCon 2025 Agentic Debug Copilot 循环: 以编译/仿真/覆盖结果为反馈的多轮规划
---
# Agentic Debug Loop (Plan-Critique-Retry)

## When To Use
- 单轮执行后仍有未解决疑点, 需要根据上次结果继续追问时
- ConversationalPlanner 的多轮规划阶段

## Method (DVCon 2025)
1. 每轮结束提取 RunReport.summary (status/failed_skills/step_count)
2. 失败技能 → 换替代技能或调整参数, 禁止原样重试
3. 成功但结论不完整 → 追加取证步骤 (波形/日志/源码交叉)
4. 三轮仍无进展 → 停止并输出已知证据清单, 不允许幻觉结论

## Steps
  1. observe(last_summary) 回喂 planner
  2. refine(plan, critique) 生成修订计划
  3. 执行并在 SQLite 落库 (可审计)
  4. 循环计数 >= 3 时强制收敛

## Pitfalls
- 每轮 critique 必须引用具体证据 (skill/信号/时刻), 不允许"再试试"
