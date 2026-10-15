---
name: generate_testbench
description: 从 UVM 1800.2-2020.3.1 标准模板生成验证 testbench (生成后必须跑合规检查)
---
# Generate Testbench (UVM 1800.2-2020.3.1)

## When To Use
- 用户提示词匹配 "生成 testbench" / "generate testbench" / "shengchen testbench"

## Method
1. 复制标准模板 (/tools/lsf_api/uvm_tb): interface(clocking+modport+SVA) /
   transaction+sequences / driver / monitor / agent / coverage / scoreboard /
   env / tests / tb_top
2. 生成后**必须**立即执行 check_uvm_compliance, 不允许跳过
3. 检查不通过 = 生成失败, 输出 ERR 与具体违规项

## Pitfalls
- 只生成不检查视为未完成; 修改模板后必须重跑合规检查
