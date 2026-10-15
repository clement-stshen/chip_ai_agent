---
name: analyze_eda_log
description: EDA log 迭代分析: 自动识别 VCS编译/UVM仿真/Verdi/LSF 格式, 结构化提取问题, 分类失败, 推荐下一步 recipe
---
# Analyze EDA Logs (Iterative)

## When To Use
- 仿真/编译/Verdi/LSF 产生 log 之后, 进入下一步调试前

## Method
1. 自动识别 log 类型: vcs_compile / vcs_uvm_sim / verdi / lsf
2. 结构化提取: severity / category / source(file:line) / message / time
3. 汇总: UVM report counts, Total N error(s) warnings
4. 失败分类: failure_class (10 值枚举) → retry_strategy (refine/regenerate/escalate)
5. 推荐下一步: 映射到 agent recipe (assertion_failure_triage / uvm_verification_flow / simulation_run)
6. 结果回喂 ConversationalPlanner (observe→refine 闭环)

## 格式要点
- VCS 编译: `Error-[SV-NP]` + 次行 `./file.sv, 42 "token"` (注意错误码含连字符)
- UVM: `UVM_ERROR @ 420ns: reporter [ID] msg` + Report Summary 计数
- Verdi: `*Error* msg` + `Total N error(s), M warning(s)`
- LSF: TERM_MEMLIMIT / TERM_RUNLIMIT / exit code

## Pitfalls
- `Total N error(s)` 太泛, 不能作为 Verdi 判据 (VCS 编译 log 也含此格式)
- UVM log 里的 `** Error:` 是 SVA 行, 不应误判为编译 log
- returncode==0 不等于 PASS, 必须看 verdict
- licence 有英式拼写 licence/license, 两种都要识别
