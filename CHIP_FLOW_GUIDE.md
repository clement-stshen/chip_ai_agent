# 芯片研发深度流程指南：前端 RTL → 综合 → 后端 → Signoff

> 机器可读版本: `flow_guide.py` · MCP 工具: `chip_flow_guide` · 回归: `tests/test_chip_ai_agent.py`

## 全局主线

```text
[Spec] -> (1)前端RTL -> (2)综合 -> (3)后端PD -> (4)Signoff -> [Tape-out]
          architecture   constraint  floorplan     MCMM STA
          RTL coding     compile x2  placement     DRC/LVS/ANT
          lint/CDC/RDC   DFT scan    CTS           power/EM/IR
          UVM 验证       LEC         routing       netlist==GDS
          formal FPV     netlist QC  ECO loops     ATPG signoff
          synth-check    QoR signoff GDS out       tape-out review
```

**核心纪律：每个相位有明确 handoff 判据；判据不满足不得进入下一相位；跨相问题走反馈环回溯，而不是在下游硬修。**

## (1) 前端 RTL（spec → 冻结 RTL）

| 项 | 内容 |
|---|---|
| 输入 | spec、ISA/总线协议、PPA 预算、CDC 约束 |
| 阶段 | 架构探索 → RTL 编码 → lint → CDC/RDC → UVM 验证 → formal → synth-check → **RTL freeze** |
| 输出 | 冻结 RTL、验证 signoff 报告、CDC waiver、lint-clean 报告、SVA、草稿 SDC |
| Handoff 判据 | lint=0（waived 已记录）· CDC unwaived=0 · 功能覆盖=100% · 回归失败=0 · P0 性质未证明=0 · synth-check WNS>=-0.5ns 且面积<=120% 估算 |
| 工具 | OSS: verilator/slang/surelog/iverilog/cocotb/sby · 商用: VCS/Xcelium/Questa/SpyGlass/JasperGold/VC Formal |
| 经典坑 | 验证未闭环交综合（bug 流到 GDS 回改代价x10）；CDC 只查不管 waiver；latch 推断/复位风格不统一；不做 synth-check 预算后爆 |

## (2) 综合（RTL → 门级网表）

| 项 | 内容 |
|---|---|
| 输入 | 冻结 RTL、SDC、目标库(.lib/.db)、UPF、DFT spec |
| 阶段 | 约束建立 → compile explore → compile final → DFT 扫描插入 → netlist QC → **LEC(RTL==netlist)** → 综合 signoff |
| 输出 | 门级网表、mapped SDC、扫描链、时序/面积/功耗 QoR、LEC 等价证明 |
| Handoff 判据 | WNS>=0（或约定的负 slack PD 余量）· LEC unmatched=0 · unmapped cells=0 · 面积<=预算 · scan DRC=0 |
| 工具 | OSS: yosys/abc/surelog · 商用: DC/Genus/Fusion Compiler、TetraMAX、Tessent、Formality/Conformal |
| 经典坑 | SDC 不完整/时钟未定义（优化错方向到 STA 才发现）；PD 线负载余量没预留（被迫回 RTL 加流水）；DFT 插入滞后；LEC 漏检时钟/复位语义 |

## (3) 后端 PD（网表 → GDSII）

| 项 | 内容 |
|---|---|
| 输入 | 门级网表、mapped SDC、.lib/.lef、tech file、UPF、IO/宏单元约束 |
| 阶段 | floorplan(die/core/IO/宏单元/电源网络) → placement → CTS → routing → timing/power/area 优化 → ECO 循环 → **GDS out** |
| 输出 | GDSII、DEF、post-route netlist、**SPEF**、CTS 报告、DRC-clean 版图、IR/EM 报告 |
| Handoff 判据 | post-route setup WNS>=0 全角 · hold WNS>=0 全角 · DRC=0 · LVS clean · antenna=0 · 利用率<=85% · IR 在预算内 |
| 工具 | OSS: openroad/librelane/klayout · 商用: Innovus/ICC2、Calibre、RedHawk/Voltus |
| 经典坑 | floorplan 挤占优化空间→拥塞→时序死环；CTS 前不做 skew/latency 预算→hold 爆炸；**ECO>2% cells 仍硬修**（应升级回综合）；SPEF 缺失/过时→signoff 虚假 |

## (4) Signoff（多角验证 + 签核 + 流片审查）

| 项 | 内容 |
|---|---|
| 输入 | GDSII、post-route netlist、SPEF、signoff SDC/corners、UPF、foundry rule deck |
| 阶段 | MCMM STA(setup/hold) → exceptions 审查 → DRC/LVS/ANT → 功耗/EM/IR → 门级等价(netlist==GDS) → ATPG/scan → **tape-out review** |
| 输出 | 签核 GDSII、全角 STA 报告、DRC/LVS waiver 集、ATPG pattern、tape-out checklist |
| Handoff 判据 | setup/hold WNS/TNS 全 signoff 角/模达标 · DRC/LVS/ANT clean（或 foundry 接受 waiver）· IR/EM 限额内 · LEC clean · ATPG>=99% · **全部 gate measured-PASS** |
| 工具 | OSS: OpenSTA/openroad/klayout · 商用: PrimeTime(PX)/Tempus、Calibre、TetraMAX/Modus、RedHawk/Voltus |
| 经典坑 | 只签单角/单模；false-path 滥用掩盖真实路径；waiver 无 traceability 被 foundry 退回；**把 NOT RUN 的 gate 当 PASS 上报**（Reporting Contract 红线） |

## 跨相位反馈环（迭代的真实原因）

| 触发 | 从 | 回到 | 动作与上限 |
|---|---|---|---|
| 验证/形式发现 DUT bug | (1)前端 | (1)前端 | fix_request 闭环：RTL 修复→复验（cap 3x + divergence 检查） |
| 综合时序/面积不收敛 | (2)综合 | (1)前端 | RTL 重构：流水/retiming/架构修改 |
| LEC RTL==netlist 失败 | (2)综合 | (2)综合 | 修综合约束/脚本重编译（max 3x） |
| post-route setup/hold 违例 | (3)后端 | (3)后端 | ECO→重布→重 STA（总预算 10x） |
| **ECO > 2% cells** | (3)后端 | (2)综合 | 升级：重新综合而非无限打补丁（max 1x） |
| signoff DRC/LVS/ANT 失败 | (4)签核 | (3)后端 | 布线/floorplan 修复环（max 2x） |
| IR/EM 违例 | (4)签核 | (3)后端 | 电源网络返工→功耗优化（max 1x） |
| 最差角在 ECO 上限后仍失败 | (4)签核 | (1)前端 | 时序升级链：PD→综合→RTL |

## Agent 中的执行入口

```text
chip_flow_guide(op=overview|phase|route)          # 本指南的机器可读版
chip_domain_flows(domain=...)                     # 每域阶段/loop-back/sign-off 门
chip_design_pipeline(op=plan|run|next|re_verify)  # 四相引擎 + 跨域闭环
```

自然语言路由（已内置）: "前端开发"→front_end_flow · "跑综合"→logic_synthesis_flow ·
"布局布线"→physical_design_flow · "签核/流片"→signoff_tapeout · "rtl2gds 全流程"→full_flow_rtl2gds
