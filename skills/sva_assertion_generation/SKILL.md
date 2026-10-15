---
name: sva_assertion_generation
description: DVCon 2025 Spec-to-SVA 方法论: 从 spec/RTL 生成候选 SVA 并用命中率/误报率反馈迭代
---
# SVA Assertion Generation (Spec-to-SVA)

## When To Use
- 需要从接口协议文档或 RTL 推导协议断言时
- spec_to_sva recipe 的执行阶段

## Method (DVCon 2025)
1. 提取接口握手信号 (valid/ready/req/ack) 与时序约束
2. 按"安全(liveness 前置)→ 死锁(握手稳定)→ 数据完整性(稳定性检查)"三类生成候选 SVA
3. 每个 SVA 必须在 FSDB 上 evaluate, 记录命中数/误报数
4. 误报 > 0 即回退修改前提条件, 不得直接放宽

## Steps
  1. get_source_code / find_interfaces 提取接口上下文
  2. 生成候选 SVA (含前提 antecedent)
  3. evaluate_multiple_assertions 在真实波形上评估
  4. get_assertion_statistics 汇总, 与 recipe 一起落库

## Outputs
- 候选 SVA 列表 (带 evaluate 结果: hit/miss/false_positive)

## Pitfalls
- 不带前提条件的 |=> 延迟断言在复位期间必然误报, 必须加 disable iff 或 antecedent
- liveness 类断言不可仿真验证, 只做形式化, 输出时必须标注 sim_only/formal_only
