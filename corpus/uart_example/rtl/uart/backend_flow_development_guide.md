# 芯片后端 Flow 全流程开发指南

> 适用对象：数字 ASIC/SoC 后端、STA、CAD/Flow 工程师。本文以 Synopsys 工具链为主线，工艺库、工具版本和 foundry sign-off rule deck 具有项目差异，命令仅作结构示例，不能替代 PDK/Foundry 手册。
>
> 参考文章：[从26篇论文看AI for EDA：生成只是起点，工程闭环才是门槛](https://www.163.com/dy/article/L307G2TM0556C9YG.html)，访问日期：2026-09-09。

## 1. 文章内容的工程化解读

文章最值得移植到后端开发的不是“让模型自动写脚本”，而是以下四条原则：

1. **工具结果才是裁判**：脚本是否生成、代码是否相似都不是成功标准；必须由 STA、DRC、LVS、IR/EM 和 post-route QoR 给出可复现证据。
2. **状态必须保留**：后端优化是跨阶段过程，应该保存 floorplan、placement、CTS、route 等 checkpoint，支持从中间状态分支和回滚。
3. **评价要后移**：早期 congestion、global timing 只能作为代理指标，候选方案最终应统一送到 post-route 和 sign-off 检查。
4. **动作必须可审计**：每次参数修改、工具版本、输入 hash、日志、QoR 和接受/拒绝原因都要记录；AI/Agent 只能提出和执行受权限约束的候选，最终签核由工程师负责。

文章提到的 PostEDA-Bench、FluxEDA、GR-Evolve、AgenticPD 分别对应：后端结果导向评测、有状态执行与回滚、工具算法演化、跨阶段 QoR 优化。它们说明了研究趋势，但论文 benchmark 的结果不能直接等同于商业 PDK 下的量产签核能力。

## 2. 总体流程与质量门

```text
规格/约束冻结
    |
RTL + IP + UPF + SDC + 库/工艺交付
    |
RTL lint / CDC / 仿真 / 形式验证
    |
综合与 DFT ----------- 逻辑等价检查
    |
Floorplan + IO + PG
    |
Placement + pre-CTS optimization
    |
CTS + post-CTS optimization
    |
Routing + post-route optimization
    |
寄生提取 SPEF
    |
Sign-off STA / SI / IR-EM / DRC / LVS / ERC / antenna
    |
ECO 闭环 -> 重新验证 -> GDS/OASIS 交付 -> 流片审查
```

每个阶段必须有四类门：

- **输入完整性**：文件存在、版本匹配、路径可追溯、hash 固定。
- **工具成功**：无 fatal/error；warning 有归属和处置结论。
- **物理/时序指标**：面积、利用率、拥塞、WNS/TNS、功耗、DRC 数量等。
- **可复现性**：同一 commit、配置和容器/环境可以重跑或解释差异。

建议将 gate 写成机器可读的 `metrics.yaml`，而不是只看日志尾部：

```yaml
stage: post_route
status: pass
constraints:
  setup_wns_ns: ">= 0"
  hold_wns_ns: ">= 0"
  max_transition: "<= library_limit"
  max_capacitance: "<= library_limit"
  drc_errors: "== 0"
  lvs_mismatches: "== 0"
artifacts:
  - routed_db
  - spef
  - sdf
  - sta_reports
  - signoff_reports
```

## 3. Flow 开发前的输入契约

### 3.1 设计输入

- RTL：完整 filelist、include path、宏定义、top module、语言标准。
- 约束：主时钟、生成时钟、IO delay、uncertainty、clock groups、false/multicycle path、max transition/capacitance/fanout。
- 工艺与库：逻辑 `.lib/.db`、物理 LEF、tech LEF、RC corner、cell purpose、antenna 数据。
- 物理信息：die/core 尺寸、IO/pin 位置、macro、blockage、利用率目标、routing layer、tap/endcap/filler/decap 规则。
- 电源设计：电压域、UPF/CPF、power intent、always-on/isolation/level shifter 策略。
- DFT：scan chain、test clock、test mode、MBIST/LBIST、wrapper、压缩逻辑和 ATPG 要求。
- Sign-off deck：DRC/LVS/ERC、density、antenna、metal fill、IR/EM、可靠性规则。

### 3.2 目录与版本策略

```text
project/
  rtl/                 # 只读输入快照
  constraints/         # SDC、MMMC、UPF
  tech/                # PDK 路径映射，不复制受限 PDK
  scripts/{common,dc,icc2,pt,star_rc,icv}/
  config/              # YAML/Tcl 参数
  checkpoints/{syn,fp,place,cts,route}/
  reports/{lint,cdc,syn,fp,place,cts,route,signoff}/
  logs/
  runs/<run_id>/
  release/             # 仅存放经过审查的交付物
```

每次 run 固定 `RUN_ID`、Git commit、工具版本、PDK release、主机环境、输入文件 hash 和随机种子。不要直接覆盖上一次结果；优化失败时通过 checkpoint 回退。

## 4. RTL/约束交接与前端质量门

### 4.1 RTL 预检查

1. 运行 Verilog/SystemVerilog lint：未驱动信号、隐式 net、锁存器、宽度截断、未完整赋值、综合不可支持语法。
2. 运行 CDC/RDC：异步输入、复位释放、跨时钟 FIFO、同步器和 handshake 必须有结构与 waiver 依据。
3. 运行仿真和形式验证：APB 协议、寄存器读写、FIFO 边界、复位、串口帧格式、中断和 loopback。
4. 与综合 top、端口方向、参数、宏定义进行一致性检查。
5. 检查 X propagation、reset 初始化假设和不可综合 test-only 代码。

### 4.2 本 UART 设计的交接重点

当前 top 是 `uart_16550`，建议在进入综合前明确：

- `PCLK` 是主时钟，APB `PSEL/PENABLE/PREADY` 的协议时序写入 SDC/验证计划。
- `RXD` 是外部串行输入；若与 `PCLK` 异步，必须确认 `uart_rx` 内部是否包含同步器，不能仅靠 timing exception 掩盖 CDC。
- `baud_o` 是否为芯片外部可观察输出。若是输出端口，需要定义 generated clock 或明确它只是功能观测信号。
- `TXD`、`IRQ`、`nRTS/nDTR/nOUT1/nOUT2`、APB 数据端口均需要 IO delay、load/drive 和工作模式约束。
- `uart_rx_fifo`、`uart_tx_fifo` 的深度、计数器边界和满/空同时发生行为需要形式/仿真证明。
- `PRESETn` 的异步/同步属性、assert/deassert 时序和所有寄存器复位覆盖要在 RDC 报告中闭环。

## 5. 逻辑综合（Design Compiler/Fusion Compiler）

### 5.1 目标

在目标库、目标时钟和真实约束下生成门级网表，同时满足面积、时序、功耗和 DFT 要求。综合不是孤立优化，必须保证后续物理实现可收敛。

### 5.2 推荐步骤

```tcl
set_app_var search_path [list ./rtl ./lib]
read_verilog -format sverilog $rtl_filelist
current_design uart_16550
link
read_sdc ./constraints/top.sdc
check_design
check_timing
compile_ultra
report_area
report_qor
report_constraint -all_violators
write -format verilog -hierarchy -output ./out/uart_syn.v
write_sdc ./out/uart_syn.sdc
write -format ddc -hierarchy -output ./out/uart_syn.ddc
```

实际项目还应接入 scan 插入/DFT、低功耗综合、物理感知综合、clock gating 和 dont_touch 策略。禁止为了消除报告而随意加 false path、过度 dont_touch 或把真实异步路径全部切断。

### 5.3 综合出口

- 网表、SDC、DDC/数据库、综合约束和 QoR 报告。
- 逻辑等价检查：RTL vs synthesized netlist。
- 时序异常清零或有批准 waiver。
- 记录面积、组合/时序单元数量、buffer 数量、功耗估算和关键路径。

## 6. Floorplan、IO 与电源规划

### 6.1 Floorplan

- 依据面积、利用率、宏单元、pin density 和目标频率确定 die/core。
- 固定 macro 位置、方向、halo、channel 和 routing blockage。
- 将高连接度模块、时钟源、APB 控制逻辑和 FIFO 物理邻近性纳入规划。
- 预留 CTS、ECO、PG strap、填充和天线修复空间。
- 检查 core aspect ratio、pin accessibility、早期拥塞和宏间通道。

### 6.2 PG 网络

- 规划 ring、stripe、mesh、standard-cell rail、macro PG pin 连接。
- 插入 tap/endcap；按工艺规则处理 well、substrate、row 和 voltage area。
- 运行早期 IR drop/EM 估算，避免 route 后才发现 PG 无法修复。
- 对多电压设计检查 isolation、level shifter、retention 和 always-on 连接。

### 6.3 Floorplan 出口

数据库、floorplan Tcl、IO 文件、macro/PG 报告、早期 congestion、power intent 检查和 checkpoint。此处建立第一个可复用分支点。

## 7. Placement 与优化

### 7.1 主流程

1. 导入综合网表、SDC、UPF、LEF/tech LEF 和 floorplan。
2. 建立 placement blockages、density screens、cell padding 和 region。
3. global placement，分析 congestion、wirelength、density 和 timing。
4. legalization，插入 tap/endcap/physical-only cells。
5. pre-CTS optimization：修复 setup、transition、capacitance、fanout 和局部拥塞。

### 7.2 重点分析

- 高扇出控制信号和 APB 地址/数据总线是否造成 buffer 爆炸。
- FIFO 数据路径、计数器和波特率分频逻辑是否形成关键路径。
- 输入输出 pin 附近是否有过密逻辑，导致 route access 失败。
- 不能只追求面积或线长；任何局部 QoR 改善都要观察后续 CTS/route 的影响。

## 8. CTS 与时钟质量

### 8.1 CTS 目标

定义 clock source、sinks、clock tree cells、NDR、route layer、skew、latency、transition 和 useful skew 策略。完成 CTS 后重新进行 setup/hold、clock DRV、pulse width、clock gating 和时钟 DRC 检查。

### 8.2 常见问题

- generated clock 未定义，导致 `baud_o` 或分频路径被错误分析。
- reset 被误当作 clock，或异步复位释放引入 RDC/hold 风险。
- clock gating test enable、scan enable 约束不完整。
- 过度 useful skew 修复 setup，却制造 hold 和 SI 问题。

CTS 出口必须保存 post-CTS checkpoint，并提供每个 mode/corner 的 skew、latency、WNS/TNS、hold 和 DRV 报告。

## 9. Routing 与 post-route 优化

### 9.1 Routing 阶段

- global route：检查拥塞热点、绕线资源和 layer utilization。
- detail route：修复短路、开路、spacing、via、min-area、antenna 和 pin access。
- route optimization：在不破坏 DRC 的前提下处理 setup/hold、transition、capacitance、串扰和功耗。
- metal fill 后重新提取寄生并重新签核，不能把 fill 前结果作为最终结论。

### 9.2 后端优化闭环

候选方案使用以下统一流程：

```text
从最近的有效 checkpoint 分支
  -> 修改一个可解释参数集合
  -> 执行 placement/CTS/route 或局部 ECO
  -> 生成机器可解析报告
  -> post-route STA + DRC/IR/EM 子集检查
  -> 满足硬门槛后比较 QoR
  -> 接受并建立 checkpoint，或拒绝并回滚
```

建议接受条件采用“硬门槛 + 加权目标”：先保证 DRC、LVS、时序和可靠性不回退，再比较面积、功耗、线长和运行时间。任何 Agent 自动修改都必须限制在白名单参数和隔离 run 目录内。

## 10. Sign-off 全套检查

### 10.1 静态时序与信号完整性

使用 PrimeTime/PrimeTime-SI 等工具覆盖所有 mode/corner：

- setup、hold、recovery、removal、min pulse width。
- max transition、max capacitance、max fanout。
- clock latency、skew、uncertainty、generated clock 和 clock interaction。
- OCV/AOCV/POCV、CPPR、SI delta delay、noise/crosstalk。
- 端点覆盖、unconstrained path、disabled path、异常路径和 waiver。
- 使用最终 SPEF；必要时输出 SDF 给门级仿真。

### 10.2 物理验证

使用 foundry 指定的 ICV/Calibre 等 sign-off 工具：

- DRC：几何、via、密度、金属、antenna、特殊器件规则。
- LVS：版图与网表一致性、端口、PG、器件和层次。
- ERC：电源、浮空、well、短接、非法连接。
- PEX：生成最终 RC/SPEF，确认抽取角、规则 deck 和版本。
- IR drop/EM：静态与动态电流场景、power domain、via 与 strap 可靠性。
- metal fill、density、seal ring、pad、ESD 和封装相关检查。

### 10.3 逻辑与物理一致性

- RTL -> synthesis netlist：Formality 等价检查。
- synthesis netlist -> ECO netlist：增量等价检查。
- final netlist -> extracted layout：LVS。
- final timing netlist 与 release netlist、SPEF、SDC、MMMC manifest 一致。
- 关键模式进行 post-layout GLS，关注 reset、APB wait state、FIFO 边界和串口时序。

## 11. ECO 与收敛策略

### 11.1 ECO 分类

- **逻辑 ECO**：修复功能或约束问题，必须重新等价、综合和 STA。
- **时序 ECO**：尺寸、VT、buffer、resizer、局部重布线；同时检查功耗、IR/EM 和 hold。
- **物理 ECO**：via、wire、metal、antenna、DRC 局部修复；必须重跑相关 sign-off。
- **金属 ECO**：仅允许在项目定义的 metal stack 和 spare cell 能力范围内进行。

### 11.2 收敛规则

每轮 ECO 固定变更集、基线报告和回归范围。不要用单个 WNS 数字判断成功：至少同时比较所有 corner 的 WNS/TNS、DRV、功耗、拥塞、DRC、IR/EM 和运行时间。超过最大迭代次数仍不能收敛时，应回到 floorplan/约束/架构决策，而不是无限叠加补丁。

## 12. 交付物与 sign-off checklist

### 12.1 必交付物

- 最终 GDSII/OASIS、最终网表、PG 版图和 seal-ring 版本。
- 最终 SDC/MMMC/UPF、LEF/DEF（按项目要求）、SPEF、SDF。
- STA、SI、功耗、IR/EM、DRC、LVS、ERC、antenna、density、metal fill 报告。
- RTL/网表等价报告、CDC/RDC 报告、DFT/ATPG 报告。
- run manifest：工具版本、PDK 版本、命令、环境、Git commit、输入 hash、checkpoint lineage。
- waiver 清单：规则编号、实例、理由、风险、批准人和有效版本。

### 12.2 放行前问题

- 是否所有 sign-off mode/corner 都有报告且 status 为 pass？
- 是否存在 unconstrained endpoint、黑盒、未解析时钟或未解释 warning？
- DRC/LVS/ERC/IR/EM 是否为零错误或有正式批准的 waiver？
- final GDS、网表、SPEF、SDC 是否来自同一数据库和同一 release？
- 是否能从 manifest 重跑关键检查？
- 是否有人审查过自动优化和所有 ECO，而不是只接受模型/脚本结论？

## 13. 面向本 UART 的最小落地计划

1. 建立 `uart_16550` 的完整 RTL filelist，确认 `uart_rx_fifo`、`uart_tx_fifo` 等模块都被综合读取。
2. 定义 `PCLK` 主时钟和 APB 输入输出延迟；确认 `RXD` 的同步策略与 `baud_o` 的时钟/观测属性。
3. 先完成 lint、CDC/RDC、APB 协议仿真、FIFO 满空形式检查，再进入综合。
4. 以小面积 core 做 baseline floorplan，保存 synthesis 和 floorplan checkpoint。
5. 在 pre-CTS、post-CTS、post-route 三个节点分别记录 UART 数据路径、IRQ、APB response 和 baud 相关路径的 QoR。
6. 最终使用 extracted SPEF 做全 corner STA，并对 loopback、复位、FIFO 边界、APB back-to-back transaction 做门级回归。
7. 只有当 DRC/LVS/STA/IR-EM/等价检查均通过，且 release manifest 完整时，才将结果视为可交付。

## 14. 推荐的 Flow 工程规范

- 所有阶段脚本幂等：重复执行不会污染输入，也不会静默复用错误数据库。
- 所有阶段都生成 `status.json`、`metrics.json` 和日志索引，CI 只读取结构化结果。
- 把工具命令封装成稳定接口，把 PDK 路径、corner、目标和策略放进配置文件。
- 每个 checkpoint 带有父 checkpoint、变更参数、工具版本和质量门结果。
- 失败自动保存现场并回滚到最近有效状态；禁止覆盖唯一可用数据库。
- 自动化系统只允许访问隔离 worktree、白名单命令和脱敏报告；发布前必须人工复核。
- 任何指标优化都必须经过后续阶段复验，避免局部 QoR 改善导致 post-route 或 sign-off 退化。

## 15. 结论

成熟的后端 flow 不是一串 Tcl 命令，而是一套从 RTL 交接、约束管理、物理实现、寄生提取到 sign-off 的证据链。文章所说的“工程闭环”在后端的具体落点就是：**阶段状态可恢复、优化结果可测量、失败原因可追溯、签核证据可复现、最终责任有人承担**。AI 可以加速搜索和报告分析，但不能替代 foundry rule deck、sign-off 工具和工程师的放行判断。
