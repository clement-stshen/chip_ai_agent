---
name: gogotb_practical_guide
description: GoGoTB 论文 (arXiv 2607.26181) 四段八阶段验证闭环实操指导: 七维度 testpoint 分解、spec 锚定覆盖模型、自适应 seed 仿真、七类缺口定向补救、三层执行控制门禁与 L1-L4 失败恢复的落地映射。
---

# GoGoTB 实操指导 (paper → practice)

理论来源: GoGoTB: Agentic RTL Verification with Specification-Grounded
Coverage Closure (arXiv 2607.26181, 2026)。本技能把论文机制映射到本 Agent
工具链的可执行动作, 并在技能包内附**自包含可执行参考引擎**
(`flow_runner.py` + `ref_model.py` + `rtl_model.py`: spec 锚定覆盖模型、
spec 推导 oracle、自适应 seed 仿真、S8 缺口闭环, 零外部依赖可直接运行
`python3 flow_runner.py golden|bug_full_msb|d12_golden|d12_fixed`)。

## 四段八阶段 ↔ 工具链映射

| 阶段 | 节点 | 本 Agent 落地 | 产出 | 门禁 |
|---|---|---|---|---|
| 规格分析 | S1 设计画像 | 精读 RTL + `chip_flow_guide phase` | 接口/结构/时序/协议/风险画像 | 无 (人工审查) |
| 规格分析 | S2 testpoint | 按 D1-D7 七维度分解 (见下) | testpoint 表 (每条绑定具名规格行为) | Soft Gate: 维度覆盖 ≥ 6/7 |
| 环境构建 | S3 覆盖模型 | bin ← testpoint 一对一锚定 | spec 锚定覆盖模型 | Soft Gate: 每条 bin 有规格溯源 |
| 环境构建 | S4 参考模型 | **仅由规格推导** (oracle 隔离, 禁看 RTL 实现) | 独立 reference model | 硬性: 参考模型代码中无 RTL 信号名 |
| 环境构建 | S5 testbench | `chip_generate_testbench` + `chip_check_uvm_compliance` | UVM 1800.2-2020 环境 | **Hard Gate: 合规 ALL PASSED (不可跳过)** |
| 随机仿真 | S6 用例生成 | 按 testpoint 组生成 directed + constrained-random | 分组用例 | Hard Gate: 编译 0 error |
| 随机仿真 | S7 自适应 seed | 逐批统计新增覆盖 bin; **连续 2 批无增益即停** | seed 批量报告 | 无 (自动终止) |
| 覆盖率收敛 | S8 缺口闭环 | 七类分类 → 定向补救 → 停滞检测 → 升级 | 收敛报告 + signoff 证据 | 不可达 bin 移出分母需写明理由 |

## 七维度 testpoint 模板 (S2)

| 维度 | 必问 | 示例 (FIFO) |
|---|---|---|
| D1 数据边界 | 边值/全深度数据完整性 | 0x00/0xFF 往返无损 |
| D2 控制流 | 满/空状态下的门控行为 | full 时写忽略; empty 时读忽略 |
| D3 时序约束 | 延迟/背靠背/复位时序 | 读延迟恰 1 拍 |
| D4 FSM 状态迁移 | 空→满、满→空、环绕 | 写16/读12/写12/读16 |
| D5 协议符合性 | 顺序/握手/互斥 | FIFO 序; full&&empty 互斥 |
| D6 错误注入 | 违反协议/任意复位/非法配置 | 空读、满写、DEPTH=12 |
| D7 微架构交互 | 实现机制自身的风险点 | 环绕位 MSB 判别; 组合读通路 |

## Spec 锚定覆盖模型 (S3) 三条规则
1. 每个 bin 必带**具名规格行为** (可引用的一句话), 不是"覆盖率数字"
2. 每个 bin 必带**溯源 testpoint id** (S2→S3 双向可查)
3. 判定条件写在仿真前 (authoring time 决定质量上限, 论文设计判断 #3)

## 七类缺口 → 定向补救 (S8)
Stimulus Gap→定向用例; Sequence Gap→多事务定向; Cross Hole→约束细化;
State Unreached→状态路由序列; Timing Dependent→周期精确激励;
Transition Gap→边沿条件用例; Seed Insufficient→seed 扩充。
**停滞检测: 补救 2 轮无改善 → 停止补救, 升级 fix_request** (不可达需移出
分母并写明规格理由; 有 SVA 违反或死锁时优先判 State Unreached)。

## 三层执行控制落地
- **L1 工具拦截**: 只用注册表内的工具 (`chip_agent_skills` 白名单); 失败工具禁原样重试
- **L2 门禁**: Hard=合规检查/编译 0 error (失败即阻断); Soft=testpoint 维度完整 +
  信号名一致性 (早失败, 多轮后降级为警告); Advisory=scoreboard 语义比对 (不阻断流程)
- **L3 失败恢复 L1-L4**: L1 最小单文件补丁 → L2 读全跨文件上下文 → L3 重构问题组件
  → L4 最小正确实现。阈值后逐级扩大, 每级重跑门禁。

## 实测数据 (FIFO, uvm_tb_gen3)
| 运行 | 覆盖率 | SVA | mismatch | 说明 |
|---|---|---|---|---|
| golden | 100% | 0 | 0 | 自适应 seed 第 2 批无增益即停 |
| bug_full_msb | 13.3% | 501 | 76 | S8 判 State Unreached → 2 轮补救停滞 → 升级; L1 补丁修复 → 100% |
| d12_golden | 0% | 0 | 53 | R1 风险兑现 (越界 X 读); L3 组件级重构 (计数式) → 100% |

## Pitfalls
- 参考模型看不得 RTL 实现 (oracle 污染会掩盖设计缺陷)
- 同拍读写判定必须用**拍前状态** (do_w/do_r 语义)
- 随机流在空 FIFO 上的读等待要有界 (否则仿真悬挂 = 假超时)
- 覆盖率 100% ≠ 签核; 继续 post_rtl_checklist 深查 (LEC/SDC/CDC/复位回归等)
