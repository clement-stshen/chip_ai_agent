---
name: uvm_methodology
description: >
  UVM (IEEE 1800.2-2020) 方法学核心技能: 类层次 / phase 机制 / objection 生命周期
  与 drain time / config_db 配置 / sequence-sequencer-driver 握手 / TLM 端口 /
  factory 与 override / reporting 与 verbosity / 寄存器层 / 编译引入约定 /
  版本差异 (1.2 ↔ 1800.2-2020)。引用本地 Accellera 参考库
  /tools/Synopsys/temp/uvm 与标准模板工程 /tools/lsf_api/uvm_tb,
  与 generate_testbench / check_uvm_compliance / run_simulation 技能衔接。
version: 1.0.0
---
# UVM 方法学 (IEEE 1800.2-2020, Accellera 参考实现)

## When To Use
- 编写 / 审查 / 重构任何 UVM 验证环境 (component / sequence / scoreboard / register layer)
- 选择 UVM 库版本或搭建编译流程 (VCS 等仿真器)
- 规划验证架构: agent 结构、覆盖率、寄存器模型
- 解读 UVM 报告 / 配置 verbosity / 处理 objection 悬挂
- 生成 testbench 后: 衔接 `generate_testbench` → `check_uvm_compliance` → `run_simulation`

## 本地参考库 (版本矩阵)

`/tools/Synopsys/temp/uvm/` 含 6 套完整 Accellera 参考实现 + 4 个 tarball:

| 版本 | 发布 | src/ 布局 | 说明 |
|---|---|---|---|
| `uvm-1.0p1` | 2011-02 | base/comps/dpi/macros/reg/seq/tlm1/tlm2 | 无 dap/, 无 deprecated/ |
| `uvm-1.1d` | 2013-01 | + deprecated/ | deprecated 默认包含, `+define+UVM_NO_DEPRECATED` 排除 |
| `uvm-1.2` | 2014-06 | + dap/ | 项目历史基线; User's Guide 1.2 |
| `1800.2-2020-2.0` | 2023-02 | base/comps/dap/deprecated/dpi/macros/reg/seq/tlm1/tlm2 + compat/ | IEEE 1800.2 首个发布版 |
| `1800.2-2020.3.1` | 2024-08 | 同上 (181 文件) | **项目标准版**; deprecated 默认排除, `+define+UVM_ENABLE_DEPRECATED_API` 启用 |
| `uvm-core-2020.3.1` | 2024-09 | 与 3.1 完全同构 | "core" 是 GitHub 仓库名, **非子集**; 仅 `$File$/$Rev$` 标记未展开 |

版本号常量: `src/base/uvm_version.svh` → `UVM_VERSION_STRING = "Accellera:1800.2:UVM:2020.3.1"`。

## 核心类层次 (src/ 实证)

```
uvm_void
└─ uvm_object                         (base/uvm_object.svh)
   ├─ uvm_transaction                 (时间/事件属性)
   │  └─ uvm_sequence_item            (seq/uvm_sequence_item.svh)
   │     └─ uvm_sequence_base → uvm_sequence #(REQ,RSP)   [1800.2 起 abstract]
   └─ uvm_report_object
      └─ uvm_component                (base/uvm_component.svh, @uvm-ieee 13.1.1)
         ├─ uvm_driver / uvm_monitor / uvm_agent / uvm_env
         ├─ uvm_scoreboard / uvm_subscriber / uvm_test
         └─ uvm_sequencer_param_base → uvm_sequencer #(REQ,RSP)
```

## Phase 机制

- **function phases** (不耗仿真时间): `build_phase`(top-down) → `connect_phase`(bottom-up)
  → `end_of_elaboration_phase` → `start_of_simulation_phase` → `run_phase`(task) →
  `extract_phase` / `check_phase` / `report_phase` / `final_phase`(top-down)。
- **runtime schedule** (task): `pre_reset → reset → post_reset → pre_configure →
  configure → post_configure → pre_main → main → post_main → pre_shutdown →
  shutdown → post_shutdown`。
- build 中只做创建与 config_db::get;连接一律放 connect(时序固定, 层次安全)。
- 通过 `uvm_cmdline_processor` / `+uvm_set_verbosity` 等 plusarg 配置。

## Objection 生命周期与 drain time

- 消耗时间的 phase (`run_phase` 及各 runtime phase) 必须有 objection:
  `phase.raise_objection(this)` → 激励 → `#drain_time`(等待在途事务) →
  `phase.drop_objection(this)`;全部 drop 后 phase 结束。
- 所有 objection drop 后, 剩余 drain time 以独立进程 fork 等待 (base/uvm_objection.svh
  的 m_drain_proc);drain 期间再次 raise 会被捕获并重启等待。
- 悬挂调试: 用 `+UVM_OBJECTION_TRACE` 定位未 drop 的 objection;`phase_ready_to_end`
  可延后 phase 结束。
- 模板示范 (`uvm_tb/tb/fifo_tests.sv`): raise → `do_stimulus()` → `#100ns` drain → drop。

## 配置: uvm_config_db / uvm_resource_db

- `uvm_config_db#(T)::set(cntxt, inst_name, field_name, value)` — **set 在 build 之前**
  (tb_top 中 `set(null, "*", "vif", vif)`);`get(cntxt, "", field_name, var)` 在
  build_phase;`exists(...)` 判存。
- 硬性约定: **vif 只经 config_db 传递, 组件内禁止硬编码层次引用**
  (check_uvm_compliance R3 检查项)。
- `uvm_resource_db` 在 1800.2 中是 deprecated wrapper (4 文件仍在);资源底层为
  uvm_resource_pool + uvm_resource #(T)。
- 3.1 优化: `apply_config_settings` 只查 `uvm_field_*` 声明的字段
  (DEVIATIONS.md 已知偏差;`+define+UVM_COMPONENT_CONFIG_MODE_DEFAULT=CONFIG_STRICT` 还原)。

## Sequence → Sequencer → Driver 握手

- driver 侧 `uvm_seq_item_pull_port` (tlm1/uvm_sqr_ifs.svh):
  `get_next_item(req)` → 按 clocking block 驱动 → `item_done(req)`(标准握手);
  不驱动时 `try_next_item` + `item_done` 可选路径。
- sequencer 侧 `uvm_seq_item_pull_imp` (uvm_sqr_connections.svh) 提供仲裁与 start()。
- sequence 内标准三段: `start_item(item)` → `item.randomize()` → `finish_item(item)`;
  宏 `uvm_do / uvm_do_with / uvm_do_on* / uvm_create / uvm_send*`
  (macros/uvm_sequence_defines.svh + deprecated/macros/, 1800.2 无条件 include)。
- 1800.2 语义变化: `uvm_sequence_base`/`uvm_sequence #()` 变 abstract
  (必须派生);sequence 响应晚于 termination 由 error 降级为 warning;
  driver `seq_item_port` 未连接时报警 `DRVCONNECT`。

## TLM 端口

- **TLM-1**: put/get/peek port/imp/export (tlm1/uvm_ports|imps|exports.svh);
  `uvm_analysis_port`(monitor 广播, 一对多);`uvm_tlm_fifo`(参考模型/scoreboard 缓冲)。
- **TLM-2.0**: `uvm_tlm2_generic_payload`(m_command/m_address/m_data/m_length/
  m_response_status/... 10 字段)+ sockets (uvm_tlm2_sockets.svh)。
- 约定: monitor 只被动采样并经 analysis_port 发布 (R5);scoreboard 用
  `uvm_analysis_imp` 接收比对 (R6);coverage 独立成 `uvm_subscriber` (R12)。

## Factory 与 override

- 注册: `` `uvm_object_utils(T) `` / `` `uvm_component_utils(T) `` /
  `` `uvm_object_utils_begin(T)...`uvm_object_utils_end `` + `` `uvm_field_* `` 字段宏。
- 创建: `T::type_id::create("name", parent)`(禁用裸 new 组件)。
- 替换: `set_type_override_by_type` / `set_inst_override_by_type`
  (如正常 driver → 错误注入 driver, 不触碰原环境)。
- 测试选择: `run_test()` + `+UVM_TESTNAME=xxx`;全局服务 `uvm_coreservice_t::get()`。

## Reporting 与 verbosity

- 宏 (macros/uvm_message_defines.svh): `` `uvm_info(ID,MSG,VERBOSITY) `` /
  `` `uvm_warning(ID,MSG) `` / `` `uvm_error(ID,MSG) `` / `` `uvm_fatal(ID,MSG) ``
  — warning/error/fatal 强制 UVM_NONE 不过滤;带 context/begin-end 变体。
- verbosity 枚举: `UVM_NONE < UVM_LOW < UVM_MEDIUM(默认) < UVM_HIGH < UVM_FULL < UVM_DEBUG`;
  plusarg `+UVM_VERBOSITY=UVM_LOW`,按 ID `+uvm_set_verbosity=comp,id,verbosity`。
- 动作控制: `set_report_severity_id_action(UVM_WARNING, "DRVCONNECT", UVM_NO_ACTION)`;
  计数/退出: `uvm_report_server::get_server()` → `get_severity_count(UVM_ERROR|UVM_FATAL)`
  (模板 report_phase 判 verdict 的方式)、`set_max_quit_count`。

## 寄存器层 (uvm_reg, IEEE 1800.2 第 18 章)

- 建模: `uvm_reg_block`(含 uvm_reg_map) → `uvm_reg` → `uvm_reg_field`;存储 `uvm_mem`。
- 访问: `uvm_reg_adapter` 桥接 uvm_reg_item ↔ 总线 sequence_item;
  `uvm_reg_predictor` 观测总线预测镜像。
- 内置 sequence (reg/sequences/): bit_bash / hw_reset / hdl_paths / mem_walk /
  mem_shared_access / access 等 9 套。
- 3.1 新增 O(1) 查找: `get_reg_by_full_name / get_field_by_full_name /
  get_block_by_full_name` (需 `+UVM_ENABLE_REG_LOOKUP_CACHE`)。
- 注意: 当前模板工程未用寄存器层 (纯 component/sequence 结构)。

## 编译引入 (VCS 约定, 与 run_vcs.sh 一致)

```bash
UVM_HOME=${UVM_HOME:-/tools/Synopsys/temp/uvm/1800.2-2020.3.1}
# 无本地副本时: tar -xzf /tools/Synopsys/temp/uvm/UVM-1800.2-2020.3.1.tar.gz -C uvm_lib
vcs -full64 -sverilog -timescale=1ns/1ps -debug_access+all \
    +incdir+"$UVM_HOME/src" -f sim/filelist.f -l comp.log -o simv
./simv +UVM_TESTNAME=fifo_smoke_test +UVM_VERBOSITY=UVM_LOW -l sim.log
```

- 用户代码: `import uvm_pkg::*;` + `` `include "uvm_macros.svh" `` (同 +incdir)。
- compat 层: `+incdir+$UVM_HOME/compat` 并编译 `compat/uvm_compat_pkg.sv`
  (uvm_compat_packer / uvm_compat_proxy_sequence / 旧事件 API)。
- DPI: 通常无需自行编译 (仿真器自带);无 DPI 环境 `+define+UVM_NO_DPI`。
- filelist 依赖序: rtl → interface → pkg → sequencer → driver → monitor → agent →
  coverage → scoreboard → env → tests → tb_top (UVM 库本身由 +incdir 隐式引入)。

## 版本迁移要点 (1.2 ↔ 1800.2-2020)

| 主题 | UVM 1.2 | 1800.2-2020 |
|---|---|---|
| deprecated API | 默认包含, `UVM_NO_DEPRECATED` 排除 | 默认排除, `UVM_ENABLE_DEPRECATED_API` 启用 |
| `uvm_sequence_base`/`uvm_sequence #()` | 可实例化 | abstract, 必须派生 |
| sequence 响应晚于终止 | UVM_ERROR | UVM_WARNING |
| 字段宏语义 | 隐含 UVM_ALL_ON | 不再隐含, `UVM_LEGACY_FIELD_SEMANTICS` 还原 |
| packer 字节流 | 稳定 | 已变, 用 uvm_compat_packer |
| `uvm_port_base::get_provided_to()` | 旧签名 | 用 `get_comp()` |
| `` `uvm_print_* `` / uvm_deprecated_defines.svh | 可用 | 已移除 (3.1 重新提供) |
| 注解 | — | `@uvm-ieee`(LRM 节号)/ `@uvm-accellera` / `@uvm-contrib` / `@uvm-compat` |

3.1 新增: 正则缓存 (`UVM_ENABLE_RE_MATCH_CACHE`, 默认关)、register 查找缓存、
实验 polling API (`UVM_ENABLE_EXPERIMENTAL_POLLING_API`)。已知 LRM 偏差见
`DEVIATIONS.md` (3 项)。

## Method — 标准验证环境构建 (10 步, 与模板 /tools/lsf_api/uvm_tb 对齐)

1. **interface**: clocking block + modport + 协议 SVA 放 interface (不放 DUT)
2. **transaction**: uvm_sequence_item + `uvm_object_utils_begin/end` 字段宏 + 约束
3. **sequence**: uvm_sequence#(item), body 内 start_item→randomize→finish_item
4. **driver**: uvm_driver, seq_item_port.get_next_item → 按 clocking 驱动 → item_done
5. **monitor**: uvm_monitor 被动采样, uvm_analysis_port 广播
6. **agent**: uvm_agent, active/passive 由 config_db (`get_is_active()`) 决定
7. **coverage**: 独立 uvm_subscriber, covergroup 与 scoreboard 分离
8. **scoreboard**: uvm_analysis_imp + 参考模型 (uvm_tlm_fifo 缓冲)
9. **env/test**: uvm_env 在 connect_phase 连 analysis 端口;uvm_test 管 objection
   生命周期;report_phase 用 severity count 判 verdict
10. **tb_top**: 时钟/复位 + config_db::set vif + `run_test()`

生成后**必须**立即跑 `check_uvm_compliance` (13 类静态规则), 再 `run_simulation`。
一键: `cd /tools/lsf_api/uvm_tb/sim && ./run_vcs.sh fifo_smoke_test`。

## Direct Reuse (直接复用)

```bash
# 从模板生成新环境 (agent 技能 generate_testbench, 或手工复制)
cp -r /tools/lsf_api/uvm_tb /path/to/my_tb
python3 /tools/lsf_api/chip_ai_agent/skills/check_uvm_compliance/check_uvm_compliance.py /path/to/my_tb
# 库引用: UVM_HOME 环境变量优先, 否则自动解压 uvm_tb/uvm_lib/1800.2-2020.3.1
```

在 ChipAgent 中: intent 含 "uvm/testbench/regression/tb/signoff" 时路由到
`uvm_verification_flow` recipe (8 阶段编排 + loop-back 上限)。

## Pitfalls

- **忘了 objection**: run_phase 立即结束/仿真挂起 — 悬挂时 `+UVM_OBJECTION_TRACE`。
- **build 里做连接 / connect 里建对象**: 违反 phase 语义, 层次可能未就绪。
- **vif 硬编码层次引用**: config_db 传递是标准, 否则复用/重挂层失败。
- **driver 不用 get_next_item/item_done**: 破坏握手, 合规检查 R4 直接判 ERR。
- **生成后跳过合规检查**: 视为未完成 (generate_testbench 技能规定)。
- **混用 1.2 与 1800.2 的 deprecated 开关**: `UVM_NO_DEPRECATED` 与
  `UVM_ENABLE_DEPRECATED_API` 语义相反, 抄旧 Makefile 会拿到错误的 API 面。
- **field 宏丢失 UVM_ALL_ON**: 1800.2 字段宏不再隐含 all_on, 打印/比较结果
  不符合预期时先查此点。
- **只生成不检查视为未完成; 修改模板后必须重跑合规检查**。
