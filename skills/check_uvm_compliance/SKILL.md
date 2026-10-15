---
name: check_uvm_compliance
description: >
  UVM IEEE 1800.2-2020 静态合规检查技能。生成 testbench 后必须立即直接复用本技能:
  运行本目录内置的 check_uvm_compliance.py 对刚生成的工程做 13 类标准规则检查,
  不通过则判生成失败。无仿真器、无 UVM 库、无网络依赖。
version: 1.1.0
---
# Check UVM IEEE 1800.2-2020 Compliance (可直接复用)

## When To Use
- **任何 testbench 生成动作之后** (强制, 不可跳过, 不可推迟)
- 修改/重构现有 UVM 环境之后
- 验证环境代码 review / 里程碑检查

## Direct Reuse (直接复用)
本技能自包含, 生成 testbench 后立即可用, 不依赖 MCP server 或仿真器:

```bash
# 对刚生成的工程直接复用 (project_root = 生成输出目录)
python3 <skill_dir>/check_uvm_compliance.py <project_root>

# 示例
python3 chip_ai_agent/skills/check_uvm_compliance/check_uvm_compliance.py /tmp/uvm_tb_gen_xxx
```

在 ChipAgent 中已自动衔接: `testbench_generation` recipe 固定第二步调用本技能,
生成 → 检查无缝执行, 无需人工触发。

## Method — 13 类 IEEE 1800.2-2020 静态规则

1. **结构配对**: class/module/package/interface/function/task/clocking/covergroup
   与对应 end 关键字数量平衡
2. **factory 注册**: 每个 extends uvm_* 的类必须有 `uvm_component_utils` /
   `uvm_object_utils`
3. **config_db**: driver/monitor 的 vif 必须经 `uvm_config_db::get` 获取,
   组件内不允许硬编码层次引用
4. **driver TLM**: 必须使用 `seq_item_port.get_next_item` → 驱动 →
   `seq_item_port.item_done`
5. **monitor 端口**: 必须使用 `uvm_analysis_port` 发布观测事务
6. **scoreboard 端口**: 必须使用 `uvm_analysis_imp` 接收并检查
7. **agent 配置**: active/passive 必须经 `get_is_active()` 判定
8. **sequence 规范**: body 内必须 `start_item` … `finish_item`
9. **interface 防竞争**: 必须有 clocking block + modport
10. **objection 生命周期**: 每个 test 的 raise/drop 必须平衡
11. **tb_top 规范**: 必须有 `uvm_config_db::set` + `run_test()`
12. **覆盖与检查分离**: covergroup 存在时必须在独立 `uvm_subscriber` 中
13. **clocking 外不驱动**: 类代码不允许 `vif.<sig> <=` 绕过 clocking block

## Outputs
- **ALL CHECKS PASSED** (exit 0) → 合规, 步骤 OK
- **FAILED + 违规清单** (exit 1) → 列出规则编号、文件、具体违规 → 步骤 ERR

## Pitfalls
- 检查必须针对**刚生成的目录**运行, 不是模板原目录
- 检查是静态规则, 不替代仿真; 仿真通过也不代表结构合规, 两者都要
- 只生成不检查 = 未完成; R1-R13 任一失败都不得宣称"符合 UVM 标准"
