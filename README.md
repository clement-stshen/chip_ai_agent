# 芯片研发与验证智能 AI Agent(基于 Synopsys MCP 技能面)

## 1. 源目录分析(`/tools/Synopsys/temp`)

| 内容 | 说明 |
|---|---|
| `mcp/` | 标准 MCP Python SDK(client + server + FastMCP),作为协议层 |
| `skills/` | **126 个技能目录**(92 顶层 + `waveform/` 3 + `design_exploration/` 33),原为 Fernet 加密(`gAAAA...`),由对应 MCP 服务端解密加载 |
| `skills_decrypted/` | **全部 126 个 SKILL.md 已解密**,已引入 Agent(见第 15 节) |
| `SKILL.tar` / `mcp_snpls.tar.gz` | 技能与 SDK 的分发包 |

技能面(从目录名归纳)覆盖 7 大域:设计探索、调试追踪(驱动链/X 传播)、
波形取证(FSDB)、断言、覆盖率收敛、功耗/UPF、源码检索。

## 2. 芯片研发与验证痛点(由该能力面反推)

1. **海量层级/信号检索慢** → 需要 hierarchical grep + "who drives X" 语义追问
2. **X 传播/未初始化 bug 定位难**,驱动链横跨 RTL 与波形 → trace_x 自动回溯
3. **断言失败分诊耗时**,失败现场分散在时间点/波形/源码 → 一键现场取证
4. **覆盖率收敛靠人工逐条判断** → 批量高亮 + 豁免辅助
5. **UPF/功耗问题隐蔽**,电源域关系复杂 → 关系图 + 时点状态核对
6. **新设计上手成本高** → 架构解释、微架构识别、接口协议发现自动化
7. **调试知识未沉淀** → Agent 输出结构化 RunReport,可入库复用

## 3. 架构

```
intent ─▶ Planner(recipes.py 意图匹配)
            │
            ▼
     Workflow(有序技能链)
            │
            ▼
   SkillRegistry(skills/ 扫描,识别加密/明文)
            │
            ▼
   McpAdapter(stdio JSON-RPC tools/call → Synopsys MCP server)
            │
            ▼
      RunReport(步骤 + 证据,可归档)
```

## 4. 使用

```bash
python3 -m chip_ai_agent.cli "trace X propagation of u_core/dout" \
    --skills /tools/Synopsys/temp/skills \
    --server <verdi-mcp-server-cmd> --args...
```

无 MCP server 时降级运行,仍可验证规划链路;接入真实 Synopsys/Verdi
MCP server 后即为可执行的调试/验证 Copilot。

## 5. 扩展方向

- 用 LLM 替换关键词匹配,实现多轮对话式规划
- ✅ RunReport 存 SQLite,沉淀"调试经验图谱"(`--db chip_agent_runs.db`,
  `--history` 查看最近运行,`--stats` 查看各技能成功率)
- ✅ SKILL.md 解析器(`SkillRegistry.parse_skill_md`):技能包解密后可提取
  name/description/sections,用于自动生成 tool call 参数
- ✅ LLM Planner 接口层(`planner.py`):`KeywordPlanner` 基线 +
  `LLMPlanner`(OpenAI 兼容 /v1/chat/completions,支持 OpenAI / Ollama /
  llama.cpp / vLLM 等本地端点),严格 JSON 输出校验,失败自动回退关键词

```bash
# 本地模型(Ollama 示例)
python3 -m chip_ai_agent.cli "who drives u_core/dout" --planner llm \
    --model qwen2.5 --base-url http://localhost:11434/v1

# OpenAI
export OPENAI_API_KEY=sk-...
python3 -m chip_ai_agent.cli "assertion failed" --planner llm --model gpt-4o-mini
```

## 6. DVCon 2025–2026 趋势迭代 (详见 `DVCON_AI_VERIFICATION_TRENDS.md`)

- ✅ 新增 3 条配方: `spec_to_sva`(Spec→SVA 生成闭环)、
  `coverage_driven_stimulus`(覆盖率驱动智能激励)、`rtl_code_review`
  (force/release/clock 风险审查)
- ✅ `LLMPlanner.refine()`: plan-critique-retry 自审, 修订失败保留原计划
- ✅ `ConversationalPlanner`: 把上次 RunReport 摘要(状态/失败技能)回喂 LLM,
  `agent.run()` 结束自动 `observe()`, 实现多轮增量规划
- ⚠️ 联网检索 API 配额耗尽, DVCon 2026 部分为推断, 待恢复后复核文档第 4 节清单

## 7. DVCon 2025 方法论技能包 (`skills/`)

基于 DVCon 2025 论文方法论生成的 6 个明文 SKILL.md (目录名即技能名,
registry 自动按域分类):

| 技能 | 对应 DVCon 趋势 | 核心约束 |
|---|---|---|
| `sva_assertion_generation` | Spec-to-SVA | 误报>0 必须回退修订; liveness 标注 formal_only |
| `assertion_feedback_refine` | 断言质量反馈环 | 零命中=无效断言; 通过率≠质量 |
| `coverage_driven_stimulus` | 覆盖率驱动智能激励 | 先分类欠激励/不可达, 不可达不消耗迭代预算 |
| `vplan_coverage_traceability` | vplan 条目↔覆盖回链 | 无 run_id 的结果不可作闭环证据 |
| `agentic_debug_workflow` | Agentic Debug Copilot | 失败技能禁止原样重试; 3 轮强制收敛 |
| `waveform_causal_diagnosis` | 因果诊断 | 驱动链与静态连通性矛盾时输出矛盾点 |

使用: `--extra-skills chip_ai_agent/skills` 合并扫描, 与加密 Synopsys 技能包共存
(总数 98, 新技能可被 `SkillRegistry.parse_skill_md` 解析出 Method/Steps/Pitfalls)。

## 8. digital-chip-design-agents 全面引入 (`digital/`, 自包含 vendored 副本)

来源: Claude Code marketplace 插件 (16 插件 / 17 明文 SKILL.md / 14 域 + 流水线编排)。
**已完整 vendor 到 `chip_ai_agent/digital/`** (上游 commit 见 `digital/UPSTREAM_COMMIT`,
MIT 许可见 `digital/UPSTREAM_LICENSE`), 不再依赖 `/tools/Synopsys/temp` 外部路径。

- ✅ **17 个领域技能默认注册**: architecture / rtl-design / verification /
  formal / synthesis / dft / sta / hls / pd / soc / memory-ip / compiler /
  firmware / fpga / infrastructure / memory-keeper / pipeline-orchestration,
  MCP server 与 CLI 默认扫描 `digital/plugins`, 无需手工配置
- ✅ **fix_request 闭环代码化** (`design_state.py`): open→claim→fixed/abandoned
  状态机、pipeline 会话、迭代上限(默认 3, 可配)、同 session 同 module+summary
  divergence 检测、pending_approval 升级门、并发保护(claimed<10min)、signoff 归档;
  MCP 工具 `chip_design_state` (op=summary/next/open/claim/close/archive)
- ✅ **两级持久记忆** (`digital_memory.py`): `<domain>/knowledge.md` +
  `<domain>/experiences.jsonl` (按 run_id upsert), 根解析对齐上游
  (arg > `CHIP_DESIGN_MEMORY_ROOT` > XDG 中央目录 > vendored 种子);
  MCP 工具 `chip_memory_search` / `chip_memory_distill` / `chip_qor_trends`
- ✅ **EDA wrapper 执行层** (`eda_wrappers.py`): 8 个输出压缩 wrapper
  (verilator/yosys/openroad/opensta/klayout/symbiflow/bambu/gem5),
  大日志→紧凑 JSON, 强制 "exit 0 ≠ pass, 必须有 TEST PASSED 标记";
  MCP 工具 `chip_eda_wrappers`; 上游 wrapper 无执行位的部署缺陷已修
  (bash 回退 + OSError 兜底, 见 `digital/plugins/infrastructure/tools/mcp-adapter.py`)
- ✅ **16 个新 recipe**: 架构评估/RTL/形式/综合/DFT/STA/PD/HLS/SoC/Memory IP/
  编译器/固件/FPGA/基础设施/fix_request 闭环/记忆维护, 触发词含中英文
- ✅ **failure_taxonomy.py**: 移植 10 值 `failure_class → retry_strategy`
  权威映射 (meta 技能), 附关键词粗分类; agent.run 失败自动归类落经验库
- ✅ **pipeline.py**: 8 阶段 UVM 流水线机, 移植 loop-back 表
  (build FAIL→重试 3x; coverage gap→constrained_random 5x; signoff FAIL→3x;
  directed_tests DUT bug→fix_request 升级), 上限耗尽带完整状态升级
- ✅ **experience.py**: JSONL 经验记忆 + TF-IDF 检索 (stdlib-only, 对齐
  experience_search.py 契约); `--experience memory/experiences.jsonl` 开启:
  失败运行自动记录 (failure_class/retry_strategy/failed_skills),
  下次 plan() 自动注入 top-3 相关历史
- ✅ 新 recipe `uvm_verification_flow`: 8 阶段序列 + 各阶段 loop-back 预算标注

## 8.1 本轮缺陷修复 (回归测试 `tests/test_chip_ai_agent.py`)

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | 触发词 `"x"` 子串误匹配 ("mux issue"→x_prop_debug) | 短 ASCII 触发词按词边界匹配 (`_trigger_hit`) |
| 2 | McpAdapter 被 server stdout 噪声行一击断连, legacy 回退失效 | 坏行跳过不丢流; stderr 重定向; 实测 banner 场景存活 |
| 3 | UVM mismatch/timeout 误分类为 tool_error→regenerate | 补 mismatch/timeout/uvm_error hints; severity 纳入分类文本 |
| 4 | SVA 断言正则永不匹配 (re.X 吃掉字面空格) | `assertion\s+failed`; source 补齐 file:line |
| 5 | `chip_agent_run` 恒 isError=False | 失败/空计划传播 isError=True |
| 6 | LLM planner 重排序被静默丢弃 | 按决策顺序执行子集 |
| 7 | 默认注册无 DB/经验库, 数据飞轮关闭 | server 默认落 `chip_agent_runs.sqlite3`/`experiences.jsonl`, `.mcp.json` 显式声明 |
| 8 | run context 广播到每一步 | 按各本地工具声明的参数键过滤 |
| 9 | `target: [a, b]` 多目标解析失败 | 取第一个规范 target |
| 10 | vendored mcp-adapter OSError 崩溃 + wrapper 无执行位 | bash 回退 + OSError→FAIL; 执行位已修 |

## 8.2 架构全面对齐 (spec→tape-out 链路成型)

对齐 digital-chip-design-agents 的四层架构, 全部代码化强制执行:

| 层 | 模块 | 能力 |
|---|---|---|
| **域全覆盖** | `domain_flows.py` | 15 个域 (14 设计域 + infrastructure) 的阶段序列、loop-back 表(含上限)、sign-off 门、checkpoint 位置、工具路由, 从 16 个 orchestrator 机器可读化; `pipeline_plan()` 给出 14 段 spec→tape-out 主线+分支 (architecture→rtl→soc/memory-ip/compiler/hls→verification→firmware/fpga→formal→synthesis→dft→pd→sta) |
| **域内执行** | `design_pipeline.py` `DomainFlowRunner` | 阶段执行 + loop-back 上限强制; 无规则/上限耗尽→带完整状态升级; DUT bug 走 fix_request 交接而非本地重试; sign-off checkpoint 人审门 (`pending_approval`); 每阶段写 design_state `history[]` 10 字段 trace; 每次终止路径写域级 experiences.jsonl (上游 schema) |
| **跨域闭环** | `CrossDomainDriver` + `design_state.py` | dispatch_rtl → claim → fixed → re_verify → cap/divergence → archive, 验证↔RTL 反馈环全代码化 |
| **Reporting Contract** | `reporting.py` | exit 0 ≠ pass; 未运行的 gate = NOT RUN 永不报 PASS; measured/inferred 分离; FAIL/WARN 必带 failure_class+retry_strategy; signoff 仅当全部 gate measured-PASS; `gate_from_wrapper()` 直接消费 wrapper JSON |
| **基础设施** | `infra_detect.py` + `eda_wrappers.py` | 24 开源 + 7 商用(detect-only) 检测 + 8 wrapper + 11 MCP 配置部署状态; wrapper 执行层强制 pass-marker 判定 |
| **记忆** | `digital_memory.py` + agent 集成 | 两级记忆全链路: 规划时自动注入匹配域的 knowledge + 相关经验 (`plan.domain_knowledge_preview/domain_experience`); 运行后按域落 experiences |

**MCP 工具 (19 个)**, 新增:
- `chip_design_pipeline` — plan/status/run/next/re_verify (spec→tape-out 引擎)
- `chip_domain_flows` — 任意域的阶段/loop-back/sign-off/工具查询
- `chip_infra_detect` — 基础设施对齐检测

流水线执行语义: `run` 接受 `stage_results` 外部结果映射;
未提供的阶段按 Reporting Contract 记为 NOT RUN→FAIL, 绝不虚报 PASS。

## 9. "生成 testbench" 提示词 → 强制 UVM IEEE 1800.2-2020 合规检查

当意图匹配 `生成 testbench / 生成testbench / shengchen testbench /
generate testbench / build testbench / 创建 testbench / 生成验证环境` 时,
触发 `testbench_generation` recipe, 固定两步且**检查不可跳过**:

1. `generate_testbench` — 从 `/tools/lsf_api/uvm_tb` 标准模板
   (UVM 1800.2-2020.3.1) 生成完整环境 (interface+clocking+modport+SVA /
   transaction+sequences / driver / monitor / agent / coverage /
   scoreboard / env / tests / tb_top)
2. `check_uvm_compliance` — 针对**刚生成的目录**强制执行 9 类静态合规检查
   (结构配对 / factory 注册 / config_db / seq_item_port / analysis_port /
   analysis_imp / active-passive / objection 平衡 / clocking+modport);
   不通过则该步骤报 ERR 并列出具体违规

实现: `local_tools.py` 本地工具层 (不走 MCP), `agent.py` 中本地工具优先、
MCP 兜底; 内置方法论技能目录默认加载, 开箱即用。

### check_uvm_compliance 技能 (自包含, 可直接复用)

`skills/check_uvm_compliance/` 技能包内置独立检查脚本, **不依赖 Agent/
MCP/仿真器/UVM 库**, 生成 testbench 后任何环境都能直接复用:

```bash
python3 chip_ai_agent/skills/check_uvm_compliance/check_uvm_compliance.py <project_root>
```

检查规则从 9 类扩展到 **13 类** (R1-R13): 结构配对(含 clocking 声明去重) /
factory 注册 / config_db / seq_item_port / analysis_port / analysis_imp /
get_is_active / start_item-finish_item / clocking+modport / objection 平衡 /
tb_top 规范 / coverage-scoreboard 分离 / clocking 外禁止直接驱动。
Agent 内 `testbench_generation` recipe 第二步自动调用该技能内置脚本,
生成 → 检查零手工衔接。

## 10. 集成到 Claude Code / Codex / VS Code (详见 `INTEGRATION.md`)

`mcp_server.py` 为**双模式 MCP server**:
- **SDK 模式 (默认)**: 构建在官方 MCP Python SDK v2 (`MCPServer`) 之上 —
  24 个工具全部带 tool annotations (只读工具 `readOnlyHint` 可并行调用)、
  类型化输入校验、长操作 progress 上报、10 个 resources、2 个 prompts、
  可选 streamable-HTTP (团队共享)。安装: `bash chip_ai_agent/install_sdk.sh`。
- **Legacy 模式 (自动回退)**: 零依赖 stdio JSON-RPC (纯标准库, 与
  mcp_adapter 对称), SDK 不可导入时自动启用。

单一事实源 `mcp_tools.py::TOOL_DEFS` 同时驱动两种模式;领域逻辑不变,仅
`agent.py`(操作锁+逐步进度回调)与 `report_store.py`(WAL+线程锁)做并发安全
小改 (SDK 并发调用安全)。回归: 54 tests 全绿 (41 存量 + 13 SDK 特性)。

```bash
bash chip_ai_agent/install_integration.sh   # 一键注册双端 + 安装技能
```

已在本机**真实验证**:
- Claude Code: `claude mcp list` → chip-agent Connected;
  headless 调用 `chip_agent_plan("生成 testbench")` → `testbench_generation` ✔
- Codex: `codex mcp list` → chip_agent enabled;
  `codex exec -s danger-full-access` 调用 → `(completed)` ✔
- SDK 模式: stdio 协议直测 + streamable-HTTP 冒烟 (20 tools / 4 resources /
  2 prompts 经网络调用) ✔;无 SDK 环境自动回退 legacy (20 tools 可用) ✔
- 技能: 8 个 SKILL.md 安装到 `~/.claude/skills` 与 `~/.codex/skills`
- 工程级: `/tools/lsf_api/.mcp.json` (VS Code Claude/Codex 插件复用同一配置)

## 11. 真实工程检验: Verification Academy UART 16550

用 `/tools/Synopsys/temp/uart_example` (Coverage Cookbook 级参考工程:
3 agent + 5 coverage monitor + 3 scoreboard + 寄存器模型 + 8 测试, 89 文件)
检验 AI Agent 的 `check_uvm_compliance` 能力, 并**反哺修复检查器 4 个缺陷**:

| 修复 | 说明 |
|---|---|
| extern 类外声明 | `extern function/task` 是声明不是块开头, 不再误计 |
| covergroup 采样 | `with function sample(...)` 不再误计为函数体 |
| 字符串字面量 | `uvm_error("... interface ...")` 中的词不再参与结构配对 |
| R7/R10 误报 | 接受 config-object 式 active/passive (`uvm_active_passive_enum`);
  无 run_phase 的 base test 豁免 objection 检查 |

结果: 违规 53 → 10 → **1 项真实阳性**:
`R9 interface: missing clocking block or modport`
(4 个 interface 均无 clocking block/modport — 该工程 2013 年老风格,
确实存在采样竞争风险, 属真实偏离而非误报)。

FIFO 模板与生成目录回归: ALL CHECKS PASSED, 无退化。
MCP 链路 (`chip_check_uvm_compliance`) 对真实工程 E2E 验证通过。

## 12. 资料需求与数据质量 (详见 `DATA_REQUIREMENTS.md`)

**提升 Agent 需要的资料** (按组件映射, 完整清单见文档):
- Planner: 历史意图→recipe 配对、调试工单文本、真实 MCP tools/list 输出
- Skills: **✅ 已获得: 126/126 个 SKILL.md 全量解密并引入 (第 15 节)**; 仍缺: 断言库、覆盖率报告样例
- Experience: 真实失败案例 (schema 见文档, 含根因与修复动作)
- Testbench: 更多 DUT 参考 (APB/SPI/I2C)、内部 UVM 编码规范
- LLM: 200+ intent→plan 标注对 (few-shot / 本地模型微调)

**脏数据清洗** (`data_quality.py`, backup-first):
```bash
python3 chip_ai_agent/data_quality.py --experience exp.jsonl --db runs.db          # 审计
python3 chip_ai_agent/data_quality.py --experience exp.jsonl --db runs.db --clean  # 清洗
```
处理 8 类脏数据: 无信息记录 / LLM 降级环境噪音 / 重复 / 畸形行 /
空 run / 孤儿 steps / 陈旧生成目录 / 加密技能误计。
已用真实脏数据验证: `/tmp/exp_test.jsonl` (info_free=1) 与
`/tmp/exp_runs.db` (empty_run=1) 审计→清洗→复审闭环通过;
单元自测覆盖全部 5 类经验脏数据 (只保留真知识记录)。

## 13. EDA 工具调用层 (VCS / Verdi / NPI)

基于 `/tools/Synopsys/temp/NPI` 分析 (Synopsys 官方编程接口套件:
C 头文件 24 个 / pynpi Python 绑定 / verdilearn agentic 层 / FSDB 示例)
新增 `eda_tools.py`, 让 Agent 具备真实 EDA 工具调用能力:

| 能力 | 说明 |
|---|---|
| `check_eda_tools` | 多源发现: PATH → **modulefile 声明**(本站权威来源) → 常见安装根; NPI 套件单独检测 |
| `run_simulation` | VCS 标准命令构造 + 执行 + UVM 报告解析 (TEST PASSED/FAILED, error/fatal 计数, 失败附 log 尾部) |
| `open_waveform` | Verdi 命令构造 (`-nologo -ssf <fsdb> -s <sig>`), 本机缺失给可复制命令 |
| `fsdb_inspect` | pynpi 程序化波形读取 (sig_value_at / find_x / vc_count), 需真 VERDI_HOME |

**本机环境结论**: 分析机上无 vcs/verdi 二进制 (modulefile 声明的
`/tools/Synopsys/{vcs,verdi}/Y-2026.03-SP1` 不在本机, 工具在 EDA 主机/LSF 节点),
因此所有调用**结构化降级**: 返回 `module load synopsys` 指引 + 完整可复制命令,
绝不中断。工具就位后同一接口零改动直接执行。

集成: 新 recipe `simulation_run` (跑仿真/run vcs/simulate/...),
3 个 SKILL.md 方法论技能, MCP 工具 `chip_edatools` /
`chip_run_simulation` / `chip_open_waveform` (共 10 个 MCP 工具)。
自测: recipe 匹配/Agent 链路/MCP 协议全通过; run_simulation 在工具
缺失时正确判 ERR 并携带降级信息。

## 14. EDA Log 迭代分析 (`eda_log_analyzer.py`)

对 EDA 工具产生的 log 做结构化迭代分析, 闭环 observe→refine:

| log 类型 | 解析内容 |
|---|---|
| `vcs_compile` | `Error-[SV-NP]` + 次行 `file, line "token"` (错误码含连字符), 裸 `Error:` |
| `vcs_uvm_sim` | `UVM_ERROR/FATAL @time [id] msg`, Report Summary 计数, SVA 断言失败, timeout, licence |
| `verdi` | `*Error*/*Warning*` + `Total N error(s), M warning(s)` |
| `lsf` | TERM_MEMLIMIT / TERM_RUNLIMIT / exit code |

输出: verdict (PASS/FAIL/WARN) + 结构化 issues (severity/category/source/time)
+ **failure_class → retry_strategy** (复用 10 值分类) + **推荐下一步 recipe**
(SVA 失败→assertion_failure_triage; UVM/timeout→uvm_verification_flow;
licence/LSF→simulation_run)。

开发中修复 4 个真实解析缺陷: VCS 错误码含连字符 (`SV-NP` 不匹配 `\w+`)、
两行式 Error 定位、`Total N error(s)` 误判 Verdi 优先级、UVM log 中
`** Error:` SVA 行误判编译 log; 另补 licence/license 双拼写与
MEMLIMIT/RUNLIMIT 分类提示词。

验证: 真实 Verdi log (`~/verdiLog/compiler.log`: FAIL, 1 error,
tool_error→regenerate) + 构造的 VCS 编译/UVM 失败/通过/licence/LSF 场景;
`run_simulation` 已复用分析器 (结果含 analysis 字段)。
集成: recipe `log_analysis` (分析log/analyze log/看log/日志...),
本地工具 `analyze_eda_log`, MCP 工具 `chip_analyze_eda_log` (共 11 个)。

## 15. 全量技能解密引入 + 缺陷修复 (`skills_decrypted`)

`/tools/Synopsys/temp/skills_decrypted` 下 **126/126 个 SKILL.md 已全部解密**。
本次迭代将其引入 Agent 并修复由此暴露的功能缺陷:

### 技能面引入

- **落盘**: 123 个唯一技能 (90 顶层 + 33 个 `design_exploration/` 嵌套)
  复制进 `chip_ai_agent/skills/`, 自包含不再依赖 temp 目录;
  3 个 `waveform/` 嵌套副本 (add_signals/set_radix/get_active_fsdb) 与顶层
  重名且顶层版本更全 (含 `target` 元数据), 跳过。
- **注册表** (`skill_registry.py`) 重写:
  - front-matter 全量解析: `description: |`/`>-` 多行块、`match_conditions:`
    嵌套 map、`examples:` 列表、`target` 路由元数据 (不再丢内容);
  - 重名技能 first-wins 确定性去重 (浅路径优先) + duplicates 计数;
  - `target → domain` 兜底分类 (design/waveform/power/assertion/coverage/
    statictrace/activetrace/verdimaster/onesearch/protocol), 66 个 `lang_*`/
    `netlist_*` 技能不再在领域统计中隐身;
  - 同一文件经多个根目录扫描时按 resolved path 幂等去重。
- **recipe 覆盖 100%**: 修复 2 个幻影 recipe (`coverage_driven_stimulus` 引用的
  `get_coverage_summary`/`get_uncovered_expressions`、`rtl_code_review` 引用的
  `find_release_statements`/`find_clock_driver_statements` 均不存在), 新增 8 个
  recipe (`waveform_forensics` / `timing_sequence` / `source_navigation` /
  `onesearch` / `trace_workflows` / `design_inventory` / `rtl_structure` /
  `design_exploration_api`), 扩充 4 个 (driver_trace/power_analysis/
  assertion_failure_triage/coverage_closure)。验证: Synopsys 123 技能
  **全部被 recipe 引用, 0 phantom, 0 孤儿**; `uvm_verification_flow` 的 8 个
  幻影阶段名映射到真实技能 (functional-verification/generate_testbench/
  check_uvm_compliance/run_simulation/coverage_driven_stimulus/
  formal-verification/vplan_coverage_traceability)。
- **MCP server** (`mcp_server.py` v1.3.0): 默认技能目录改为 Agent 自带
  `skills/` (135 技能 + 17 插件 + uvm_methodology = 153, 0 加密); `CHIP_AGENT_EXTRA_SKILLS`
  环境变量 (默认 digital-chip-design-agents/plugins, `:` 分隔); Agent 实例
  单例缓存, 不再每次调用全量重扫。

### 执行链路缺陷修复

- **McpAdapter 协议层重写**:
  - 标准 MCP 握手 (initialize → notifications/initialized), 服务端
    notification 按 id 匹配跳过, 请求 id 递增;
  - `select` + 手动行切分读管道 (修复 TextIOWrapper.readline 预读多行后
    select 误判无数据的挂死缺陷), 读超时可配置 (默认 30s);
  - 服务端崩溃/超时后自动 teardown, 下次调用重新拉起;
  - 非 MCP 服务端 (遗留 Synopsys server) 握手失败后自动重启并降级到
    旧 raw tools/call 模式。
  - 已用 mock server 验证 5 类场景: 完整握手+notification 跳过 / legacy
    降级 / 崩溃重连 / 无 server 优雅降级 / 超时强杀。
- **LOCAL_TOOLS 与注册表对齐**: `agent.plan()` 的可解析判断改为
  `registry ∪ LOCAL_TOOLS`, 消除"靠内置同名 SKILL.md 兜底"的隐性耦合。
- **StepResult 携带 target**: 每个执行步骤记录技能声明的路由目标
  (verdimaster/design/waveform/...), 接入真实 Synopsys MCP server 时可直接
  按子 agent 路由。

### 验证

```bash
python3 -m chip_ai_agent.cli "加载波形并查看占空比"   # → waveform_forensics, 13 步
python3 -m chip_ai_agent.cli "生成 testbench"          # → 生成 + 合规检查 ALL PASSED
chip_agent_plan("加载波形并查看占空比")                # MCP 链路: 13 步 0 missing
```

注册表统计: `skills=153 encrypted=0`, 11 个领域 + 11 类 target 分布
(153 = 135 包技能 + 17 插件 + uvm_methodology; 见第 16 节)。
已知边界: 15 个 digital-chip-design-agents 领域编排器技能 (architecture/
sta/dft/...) 无 recipe 引用 — 它们面向跨领域流程编排, 由 LLM 直接调用,
不进调试 recipe; `uvm_verification_flow` 的 loop-back 预算仍由 pipeline.py
执行, recipe 只负责技能映射。

## 16. UVM 参考库全面引入 (`/tools/Synopsys/temp/uvm`, 2026-10)

对 Accellera UVM 参考库目录做全量分析 (6 套完整 release + 4 tarball), 并全面
接入 agent 工具链:

- **可复用技能** `skills/uvm_methodology/SKILL.md` (v1.0.0): 类层次 (uvm_void→
  uvm_object→uvm_component 链) / phase 机制与 runtime schedule / objection 生命
  周期与 drain time / config_db / sequence-sequencer-driver 握手 / TLM 端口 /
  factory override / reporting 与 verbosity / 寄存器层 / VCS 编译引入约定 /
  1.2 ↔ 1800.2-2020 迁移对照表 / 10 步标准环境构建法 / pitfalls — 全部内容在
  库源码中实证 (含 `@uvm-ieee` LRM 节号注解)。随 install_integration.sh 安装到
  Claude Code / Codex 双端。
- **版本矩阵与解析** (`eda_tools.py`): `UVM_VERSIONS`/`uvm_versions()` 盘点 6
  版本 (uvm-1.0p1/1.1d/1.2/1800.2-2020-2.0/1800.2-2020.3.1/uvm-core-2020.3.1);
  `resolve_uvm_home()` 优先级: `$UVM_HOME` env → 工程本地 `uvm_lib/<ver>` →
  共享参考库 → 工程本地路径 (交给 run_vcs.sh 自动解压 tarball);`discover()` /
  `chip_edatools` 现在上报 UVM 库盘点 (extracted/tarball/默认版本)。
- **注册与路由**: `DOMAIN_RULES` 新增 `uvm|testbench` → `verification_flow`
  域 (uvm_methodology / check_uvm_compliance / generate_testbench 归类);
  `uvm_verification_flow` recipe 路由不变 (7 技能 8 阶段)。
- **关键事实**: uvm-core-2020.3.1 与 1800.2-2020.3.1 完全同构 (仅 `$File$/$Rev$`
  标记未展开, "core" 是仓库名非子集);1.2 用 `UVM_NO_DEPRECATED` 排除废弃 API,
  1800.2 反转为 `UVM_ENABLE_DEPRECATED_API` 启用;1800.2 起 `uvm_sequence_base`/
  `uvm_sequence #()` 为 abstract, 字段宏不再隐含 UVM_ALL_ON。

回归: `tests/test_uvm_integration.py` 7 项 (版本盘点/解析优先级/discover 上报/
编译命令/技能注册分类/front-matter 契约/路由) — 全绿, 总计 61 tests。

## 17. 主动记忆与主动学习 (2026-10, Phase 1/2)

把"只记录"升级为"记录→检索→反哺"闭环,全部零外部依赖:

- **检索质量**: 经验检索加时间衰减 (30 天半衰期) 与环境指纹 (EDA 工具集/
  UVM kit 变化自动降权 0.5);`successes()` 支持成功路径回放。
- **成功回放**: plan() 注入 `last_successful_run` (同 recipe 最近一次全绿 run
  的技能链) 与 `step_stats` (每步样本数/成功率)。
- **风险标注**: ≥3 样本且成功率 <50% 的技能进 `plan["risk"]`,附最高频
  failure_class (skill_failure_stats 矩阵)。**不重排 recipe** — 流水线门禁
  (生成→合规→仿真) 是契约,数据交给决策层 (客户端模型)。
- **失败即反思**: run 失败时先检索相似历史失败 (在写入本次记录**之前**,
  杜绝自我回显),把 retry_strategy 附进报告的 "## Learning (主动记忆)" 段 —
  下一次尝试立刻受益。
- **自动蒸馏**: 域内失败记录 ≥5 条且本次失败 → 自动触发 memory-keeper
  distillation (knowledge.md 更新),`CHIP_AGENT_AUTO_DISTILL=0` 可关。
- **结构化轨迹**: steps 表新增 failure_class/duration 列 (打开时自动迁移,
  老库兼容)。
- **LLM 接线 (Phase 3, 可选)**: `CHIP_AGENT_PLANNER=llm|conversational` +
  `OPENAI_API_KEY` 启用 LLM/多轮 refine 规划器;无 key 自动回落 keyword。

环境变量: `CHIP_AGENT_PLANNER` / `CHIP_AGENT_LLM_MODEL` /
`CHIP_AGENT_LLM_BASE_URL` / `CHIP_AGENT_LLM_TIMEOUT` / `CHIP_AGENT_AUTO_DISTILL` /
`CHIP_AGENT_AUDIT_EVERY` (巡检间隔, 默认 20 次 run) / `CHIP_AGENT_AUTO_CLEAN`
(自动清洗, 默认关)。

### 后续补齐的层 (Layer 2 剩余 / 3 / 4 / 5)

- **三层合并检索**: plan 注入 `run_history` (同 recipe 完整运行轨迹, DB 层)。
- **QoR 式回归守卫**: `recipe_success_trend` — 近期窗口成功率比早期下降 >0.2
  时 plan 注入 `recipe_regression` 警告 (纯 SQLite, 零开销)。
- **有效步骤变体沉淀**: 域内成功 run 的技能链 upsert 进
  `<domain>/successful_plans.jsonl` (successes 计数),plan 注入
  `effective_variants` 供回放。
- **技能级历史失败**: 反思段附每个失败技能的 top failure_class × 计数
  (来自结构化 DB 矩阵), 渲染模板区分两种条目。
- **重试去重**: `experience.add_if_new` — 连续相同 (intent/recipe/
  failure_class/status) 记录不追加, 原子重写末行累加 `repeat_count`。
- **周期巡检**: 每 N 次 run 自动 audit (只读报告进 `learned`);
  `CHIP_AGENT_AUTO_CLEAN=1` 时执行 data_quality 清洗。
- **静默失败可见化**: 学习类 best-effort 块全部接入
  `chip_ai_agent.learning` logger, 不再吞异常 (已因此抓到并修复
  digital_memory 缺 time 导入的隐藏 bug)。

### 闭环收口 (试错轨迹 / recipe 自进化 / 启动巡检)

- **试错轨迹**: 每次 run 记录 `attempt` (同 intent+recipe 的连续尝试序号,
  DB 推算, 交叉意图即重置), 渲染进报告头 `Attempt: N`, 并随 summary 写入
  经验记录。
- **recipe 自进化**: 成功变体真正驱动规划 — 当 `effective_variants` 或
  `last_successful_run` 的技能链是当前可执行步骤的**置换** (所有门禁仍运行,
  只学习顺序) 时, 自动重排 `plan["steps"]` 并附 `plan["replay"]` 溯源
  (source/run_id/order)。子集变体 (会跳过门禁) 与同序变体不生效。
- **启动巡检**: streamable-HTTP 常驻部署在 lifespan 中预热 agent 后执行
  只读 boot audit (memory/DB 健康) + **未蒸馏记录提醒** (experiences 比
  knowledge.md 新且 ≥5 条的域进 log, 提示 distill), 失败不进 wire。

### 全面复查补齐 (对照原始提案逐项核对)

- **steps 表第三列 `retry_strategy`**: 补列 + 迁移 + 落库 + `run_steps`
  回读;反思的技能级条目渲染 `历史策略: refine/regenerate/...`。
- **试错对比**: attempt>1 时报告注入 `上次尝试 (run #N): 失败技能 [...]`,
  并检测 recipe 漂移 (上次与本次路由不一致时标注)。
- **成功重排的"替换"与向量检索**: 有意留白 — 重排由证据驱动的变体回放
  替代 (更稳, 且带溯源); 替换需要可替代 skill 映射数据 (待积累);
  向量检索待 JSONL >1k 条时启用 (当前 TF-IDF 足够)。

回归: `tests/test_memory_learning.py` 30 项 — 总计 95 tests。

## 18. NPI + Synopsys MCP 栈全面引入 (2026-10, 深度解密分析)

对 `/tools/Synopsys/temp/{NPI,mcp}` 与 Synopsys MCP 组件
(verif-agent-mcp / muilt-agent-hub / copilot MCP) 做全量反解分析后的整合:

### NPI 本地波形执行层 (`npi_tools.py`)

- **库实证**: pynpi (SWIG) 的 `.so` 自带 RUNPATH=`$ORIGIN/..`,仅需
  `PYTHONPATH=NPI/python` 即可 import(venv 3.12 实测通过);激活门是
  `npisys.init` 读取真实 `$VERDI_HOME/bin/npi` — **绝不伪造该文件绕过
  授权门**,真实 Verdi (EDA 节点 `module load synopsys`) 才能激活,否则
  全部工具按统一契约优雅降级 (error/setup/env_needed/ready_command)。
- **21 个波形/层次/文件技能本地化** (LOCAL_TOOLS + agent 白名单):
  会话族 (load/get_active/set_active_fsdb — 常驻 NpiWorker JSON 行协议)、
  查询族 (value_at/first/last/transition/value_change/nth/duration/
  switching_statistics/unknown-x/sequence(SigValueEval)/max_latency)、
  层次近似 (scope 树 instance/hierarchy)、纯文件工具 (read_specific_lines/
  search_in_source_code_result)。
- 设计侧技能 (module defs/ports/source mapping) 需 VCS 编译库,维持降级
  (已在 SKILL 映射表逐项标注)。

### Synopsys verif-agent-mcp 全面接入

- **4 个远程技能注册** (run_vcs_simulation / diagnose_sim_log /
  analyze_coverage / generate_uvm_env,SKILL.md + registry 可见),
  新 recipe `verif_agent_flow` (仿真→诊断→覆盖闭环)。
- **`/tools/lsf_api/.mcp.json` 注册 verif-agent 为第二个 MCP server**
  (stdio + stub 后端) — Claude Code/Codex 直接可见其 4 工具。
- **mcp_adapter 升级**: env= 子进程环境注入 + url= streamable-http 传输
  (SDK Client 双传输)。实测直连 `/opt/verif-agent-mcp/venv/bin/verif-agent-mcp`
  (stdio+stub) → run_vcs_simulation 返回真实 SimResult(status=pass)。
- **chip_edatools 上报** `verif_agent_mcp` (installed/config/stdio_command)
  与 `npi` (importable/ready/requires) 块。

### 解密面归档

- Verdi 技能 Fernet 密钥与解密链路已在 `/tools/Synopsys/temp/re_scripts/`
  (decrypt_all.py),解密产物 `skills_decrypted/` (92 目录/126 SKILL.md);
  muilt-agent-hub 的 Fernet 仅用于 API key 加密,与技能无关 (密钥来源
  `FERNET_KEY` env)。skills 密钥仅用于读取客户自有授权技能面,不外泄。

回归: `tests/test_npi_verif_agent.py` 12 项 — 总计 115 tests。
