# chip-ai-agent 集成指南: Claude Code / Codex / VS Code

本 Agent 通过 **MCP (Model Context Protocol)** 暴露给任何支持 MCP 的客户端。
服务端为**双模式架构**:

- **SDK 模式 (默认)**: 构建在官方 MCP Python SDK v2 (`MCPServer`) 之上 —
  标准能力协商、类型化输入校验、tool annotations、progress 上报、
  resources/prompts、可选 streamable-HTTP 传输。
- **Legacy 模式 (自动回退)**: 零第三方依赖 (纯标准库) 的 stdio JSON-RPC
  循环,SDK 不可导入时自动启用 (或 `CHIP_AGENT_MODE=legacy` 强制)。

已在 **Claude Code 与 Codex CLI 上真实调用验证通过**;58 个本模块回归测试
覆盖两种模式 (stdlib 协议直测 + SDK 特性/缓存断言)。

**SDK 安装**: 由 `install_sdk.sh` 完成 (源路径经 `CHIP_MCP_SDK_SRC` 配置)
官方源码树 (git rev `754254c0`,版本 `mcp 2.3.1.dev9+754254c0` +
同源 `mcp-types`)。monorepo 内部 `mcp-types` 需与 `mcp` 同 checkout 安装
(`install_sdk.sh` 已处理);PyPI 回退路径为 `mcp==2.3.0`。

## Reporting Contract 全景 (Reporting Contract #1–#8, code-enforced)

| # | 契约 | 执行点 | 失败行为 |
|---|---|---|---|
| 1 | exit 0 / verified=false / 不可解析输出 **不是** pass | `gate_from_wrapper()`: 仅 `verified=True` 记 measured-PASS | passed=False 或 None (NOT RUN) |
| 2 | 未运行的 gate 报 **NOT RUN** (passed=None), 永不伪报 PASS | `Gate.passed: bool \| None`; `signoff_ok()` 要求 `passed is True` | signoff 直接判 false |
| 3 | measured 证据与 inference 分离 | `Gate.inferred` 显式标注; `to_dict()` 输出 `measured` 字段 | inferred gate 永不计入 signoff (design_pipeline `_signoff_gate`) |
| 4 | FAIL/WARN 必带 failure_class + 映射 retry_strategy | `StageReport.__post_init__` (#4) + `retry_strategy` property | 缺失 → ContractViolation |
| 5 | signoff 仅当**全部声明 gate** measured-PASS | `StageReport.signoff_ok()` / `DomainFlowRunner._signoff_gate` | 缺门→"unmeasured" escalate; 失败/推断门→"not measured-PASS" escalate |
| 6 | failure_class ∈ taxonomy 枚举 | `StageReport.__post_init__` (#6), FAILURE_CLASS_MAP | 非法枚举 → ContractViolation |
| 7 | measured-PASS 必带 criterion (可审计) | `Gate.__post_init__` (#7) | 空 criterion → ContractViolation |
| 8 | measured-PASS 必带 evidence (可复核) | `Gate.__post_init__` (#8), 先于 #7 执行 | 空 evidence → ContractViolation |

补充: wrapper 门命名空间为 `wrapper:<tool>` (Step 23 统一), 被 design_pipeline
taxonomy 审计豁免; 中间 gate 杂名不会阻塞 signoff 但会在 reason 中给出诊断。

## 安装 SDK (开启 SDK 模式)

```bash
bash /tools/lsf_api/chip_ai_agent/install_sdk.sh          # 本地源码树安装 (默认)
bash /tools/lsf_api/chip_ai_agent/install_sdk.sh --pypi   # 或 PyPI 发布版 mcp==2.3.0
```

安装到共享 venv (`/tools/lsf_api/.venv`,即 PATH 上的 `python3`)。不安装也
可用 — 服务端自动退回 legacy 模式,行为与之前完全一致。

## 快速安装 (一键, 幂等)

```bash
bash /tools/lsf_api/chip_ai_agent/install_integration.sh
```

自动完成:
1. Claude Code 注册 MCP server (user 级, `~/.claude.json`)
2. Codex 注册 (`~/.codex/config.toml` 的 `[mcp_servers.chip_agent]`)
3. 12 个内置方法论 SKILL.md 技能安装到 `~/.claude/skills/` 和 `~/.codex/skills/`
   (`--all` 追加安装全部 123 个 Synopsys/Verdi 技能)
4. 健康检查

## 暴露的 MCP 工具 (24 个, 全部带 tool annotations)

| 工具 | 功能 | 只读 |
|---|---|---|
| `chip_agent_plan` | 意图 → recipe/步骤/缺失技能规划 | ✔ |
| `chip_agent_run` | 执行工作流 (含生成 testbench + 强制 UVM 合规检查), **逐步 progress** | |
| `chip_generate_testbench` | 从 UVM 1800.2-2020.3.1 模板生成验证环境 | |
| `chip_check_uvm_compliance` | IEEE 1800.2-2020 13 类静态合规检查 | ✔ |
| `chip_agent_skills` | 技能注册表与领域分布 | ✔ |
| `chip_agent_history` | 最近运行记录 (需 `CHIP_AGENT_DB`) | ✔ |
| `chip_agent_stats` | 技能成功率统计 (需 `CHIP_AGENT_DB`) | ✔ |
| `chip_edatools` / `chip_run_simulation` / `chip_open_waveform` / `chip_analyze_eda_log` | EDA 工具发现 / VCS 仿真 / Verdi 波形 / log 分析 (仿真带 progress) | 除仿真外✔ |
| `chip_design_state` | 验证↔RTL 闭环 fix_request 状态机 (summary/next/open/claim/close/archive) | |
| `chip_memory_search` | 域级经验记忆检索/写入 (experiences.jsonl TF-IDF + knowledge) | |
| `chip_memory_distill` | 经验蒸馏到 knowledge 摘要 (memory-keeper) | |
| `chip_agent_recall` | **主动记忆召回**: 一次只读调用捞齐 intent 相关的全部记忆 (经验/域知识/域记录/有效变体/技能风险策略) | ✔ |
| `chip_qor_trends` | 跨 run QoR 指标趋势与回归检测 | ✔ |
| `chip_design_pipeline` | spec→tape-out 引擎: plan/status/run/next/re_verify (域内 loop-back + 跨域闭环 + checkpoint 门) | |
| `chip_domain_flows` | 15 域机器可读流程查询 (阶段/loop-back 上限/sign-off 门/工具路由) | ✔ |
| `chip_infra_detect` | EDA 环境检测: 仅 Synopsys/Cadence/Siemens + 非 EDA 主机工具分列; 不安装或部署替代工具 | ✔ |
| `chip_flow_guide` | 四相芯片研发流程 (前端RTL→综合→后端→Signoff); route 按 intent 定位 | ✔ |
| `chip_ug_search` | VCS+Verdi 官方 UG 手册向量检索 (哈希TF-IDF, 128 docs/34.5k chunks); 附 product/doc/chunk 出处 | ✔ |
| `chip_npi` | Synopsys NPI C API 检索: 24 头文件/506 API (FSDB/覆盖率/UPF/VCS/NL/VerdiLearn); families/search/get | ✔ |
| `chip_examples` | 黄金 UVM TB 范例库 (uart_example: APB/UART/modem 三agent, 89 文件12类); list/search/get | ✔ |

只读工具标注 `readOnlyHint=true, destructiveHint=false`,客户端可安全并行调用。
所有工具 `destructiveHint=false` (该工具面不删除任何用户数据)。
长操作 (`chip_agent_run` 逐步 / `chip_run_simulation` /
`chip_memory_distill` / `chip_qor_trends` / `chip_check_uvm_compliance`) 通过
MCP progress 通知实时上报进度。

## Resources (7 个, SDK 模式)

| URI | 内容 |
|---|---|
| `chip://skills` | 全部 160 个技能与领域分布 (含 uvm_methodology/语料技能) |
| `chip://skills/{domain}` | 单领域技能清单 |
| `chip://runs` | 最近运行记录 (report store) |
| `chip://design/state` | design_state.json 摘要 |
| `chip://flows/{domain}` | 单域机器可读流程 |
| `chip://memory/{domain}` | 单域蒸馏知识 + 学习到的有效技能链 (experiences 蒸馏产物) |
| `chip://guide` | 四相流程总览 |
| `chip://ug` | UG 向量索引状态 (文档数/chunk 数/大小/是否已构建) |
| `chip://npi` | NPI C API 族谱总览 (24 头文件/506 API 分布) |
| `chip://examples` | 黄金 TB 范例分类总览 (uart_example) |

## 主动记忆 & 主动学习 (五层闭环)

| 层 | 机制 | 触发点 |
|---|---|---|
| 1 经验注入 | `chip_agent_plan` 自动附带 past_experience (按新近度/环境指纹加权) | 每次规划 |
| 2 主动召回 | `chip_agent_recall` 一次捞齐经验+域知识+域记录+有效变体+技能风险策略 | 客户端开工前主动调用 (调试 prompt 第 0 步) |
| 3 失败反思 | 失败 run 自动附加相似历史失败及其修复策略 (`report.reflections`) | 每次失败 |
| 4 成功沉淀 | 通过全部门的技能链自动固化为域 "有效步骤变体"; 域内失败 ≥5 条自动蒸馏 knowledge.md (`CHIP_AGENT_AUTO_DISTILL`) | 每次成功/失败 |
| 5 记忆巡检 | 每 20 run 只读审计 memory/DB (experiences 超 knowledge 增长时提示蒸馏); HTTP 部署开机审计 | 周期/启动 |

记忆两级存储: `<root>/<domain>/experiences.jsonl` (逐 run 经验) +
`knowledge.md` (memory-keeper 蒸馏); 根目录由 `CHIP_DESIGN_MEMORY_ROOT`
控制, 知识只补缺不覆盖; 环境指纹变化时旧经验自动降权 (工具升级不污染)。

## Prompts (2 个, SDK 模式)

- `chip-plan` — 芯片验证/调试任务规划提示词
- `chip-debug` — 芯片调试多步工作流提示词

## Claude Code (CLI)

注册 (install_integration.sh 已做, 手工方式):
```bash
claude mcp add chip-agent -s user -- python3 /tools/lsf_api/chip_ai_agent/mcp_server.py
claude mcp list        # 应显示 chip-agent - Connected
```

调用 (交互模式直接说, 或 headless):
```bash
claude -p "用 chip-agent 生成 testbench 到 /tmp/my_tb"
# 工具级: mcp__chip-agent__chip_agent_plan / chip_agent_run / ...
```
已验证 E2E: `chip_agent_plan("生成 testbench")` → `testbench_generation` ✔

工程级配置: `/tools/lsf_api/.mcp.json` (放入任意工程根目录即项目级生效)。

## streamable-HTTP (团队共享, SDK 模式)

```bash
CHIP_AGENT_TRANSPORT=streamable-http CHIP_AGENT_PORT=8000 \
  python3 /tools/lsf_api/chip_ai_agent/mcp_server.py

# 客户端注册
claude mcp add chip-agent-http --transport http http://127.0.0.1:8000/mcp
```

服务端启动时预热 agent 单例 (160 技能注册表扫描), 所有客户端首个调用即热。
默认仍为 stdio,对现有 `.mcp.json` 零影响。

## Codex (CLI)

`~/.codex/config.toml`:
```toml
[mcp_servers.chip_agent]
command = "python3"
args = ["/tools/lsf_api/chip_ai_agent/mcp_server.py"]
```

调用:
```bash
codex                      # 交互模式直接说
codex exec -s danger-full-access "用 mcp__chip_agent__chip_agent_plan 规划: 生成 testbench"
codex mcp list             # 应显示 chip_agent enabled
```
已验证 E2E: `chip_agent/chip_agent_plan (completed)` → `testbench_generation` ✔
(非交互 exec 需 `-s danger-full-access` 或交互模式批准工具调用)

## VS Code

### Claude Code 插件 (Anthropic)
安装 "Claude Code for VS Code" 扩展后, 它直接复用 Claude Code 的 MCP 配置
(user 级已注册, 或工程 `.mcp.json`)。在侧边栏 Claude 面板中:
1. 打开任意工程 (建议把 `/tools/lsf_api/.mcp.json` 复制到工程根)
2. 输入 "用 chip-agent 生成 testbench" — 工具自动出现并可调用

### Codex 插件 (OpenAI)
安装 "Codex – OpenAI's coding agent" 扩展后, 它复用 `~/.codex/config.toml`
中的 `mcp_servers.chip_agent`。在 Chat 面板选择 Codex, 同样直接说
"用 chip-agent 生成 testbench"。

### 通用
任何支持 stdio MCP 的 VS Code 扩展 (Continue / Copilot MCP 等) 都可用
`.mcp.json` 的同款 JSON 注册。

## SKILL.md 技能 (已安装到双端)

安装后 Claude/Codex 在匹配场景自动加载方法论, 无需显式调用:
- `check_uvm_compliance` — 生成 testbench 后强制复用的合规检查
- `generate_testbench` — UVM 1800.2-2020.3.1 模板生成
- `sva_assertion_generation` / `assertion_feedback_refine` — DVCon Spec-to-SVA
- `coverage_driven_stimulus` / `vplan_coverage_traceability` — 覆盖闭环
- `agentic_debug_workflow` / `waveform_causal_diagnosis` — 多轮调试与因果诊断

## 环境变量 (可选)

| 变量 | 作用 |
|---|---|
| `CHIP_AGENT_MODE` | `auto`(默认, 有 SDK 用 SDK)/ `sdk` / `legacy` |
| `CHIP_AGENT_TRANSPORT` | `stdio`(默认) / `streamable-http` |
| `CHIP_AGENT_HOST` / `CHIP_AGENT_PORT` | HTTP 绑定 (默认 127.0.0.1:8000) |
| `CHIP_AGENT_STATELESS` | `1` 时 HTTP 为无状态模式 (无 server→client 通道) |
| `CHIP_AGENT_PLANNER` | `keyword`(默认) / `llm` / `conversational` (需 OPENAI_API_KEY, 无 key 自动回落) |
| `CHIP_AGENT_LLM_MODEL` / `_BASE_URL` / `_TIMEOUT` | LLM 规划器参数 (默认 gpt-4o-mini / api.openai.com / 30s) |
| `CHIP_AGENT_AUTO_DISTILL` | `1`(默认) 域内失败 ≥5 条自动蒸馏 knowledge; `0` 关闭 |
| `CHIP_AGENT_TEMPLATE_TB` | UVM testbench 模板工程 (默认 /tools/lsf_api/uvm_tb) |
| `CHIP_AGENT_MODULEFILES` / `CHIP_AGENT_EDA_ROOTS` | `:` 分隔的 modulefile 路径 / EDA 厂商根 |
| `CHIP_AGENT_NPI_ROOT` | NPI kit (pynpi+lib+inc, 默认 /tools/Synopsys/temp/NPI) |
| `CHIP_AGENT_UVM_ROOT` / `CHIP_AGENT_UVM_TGZ_ROOT` | UVM 参考库 / 1.x tarball 父目录 |
| `CHIP_AGENT_UG_ROOT` / `CHIP_AGENT_DVCON_ROOT` | UG 手册语料根 / DVCon 语料根 |
| `CHIP_AGENT_EXAMPLE_UART` | Verification Academy UART 范例树 |
| `CHIP_AGENT_VERIF_AGENT_BIN` / `_CONFIG` | verif-agent-mcp 可执行文件 / config.yaml |
| `CHIP_MCP_SDK_SRC` / `CHIP_AGENT_PYTHON` / `CHIP_AGENT_HOME` | install_sdk.sh / install_integration.sh 路径覆盖 |
| `CHIP_AGENT_SKILLS` | 主技能目录 (默认 chip_ai_agent/skills) |
| `CHIP_AGENT_EXTRA_SKILLS` | 附加技能根 (默认 chip_ai_agent/digital/plugins, 17 个 digital-agents 技能) |
| `CHIP_AGENT_DB` | SQLite 运行库 (默认 /tools/lsf_api/chip_agent_runs.sqlite3; WAL + 线程锁) |
| `CHIP_AGENT_EXPERIENCE` | experiences.jsonl (默认 /tools/lsf_api/experiences.jsonl) |
| `CHIP_DESIGN_STATE` | design_state.json 路径 (fix_request 闭环) |
| `CHIP_DESIGN_MEMORY_ROOT` | 两级记忆根目录 (默认 XDG 中央目录, 知识只补缺不覆盖) |
| `CHIP_AGENT_TOOL_CACHE_TTL` | SDK 模式只读工具结果 TTL 缓存秒数 (默认 30;`0` 关闭) |

## 直接 CLI (不经 MCP)

```bash
python3 -m chip_ai_agent.cli "生成 testbench"
python3 -m chip_ai_agent.cli "uvm regression" --db runs.db --history
```

## UG 官方手册向量检索

- **来源**: 经 `CHIP_AGENT_UG_ROOT` 配置 (VCS + Verdi Y-2026.03-SP1), 128 篇文档
- **方案**: 段落切分 (~1200 字符带重叠) → 哈希 TF-IDF 稀疏向量 (word 1-2 gram,
  dim=2^18, L2 归一化) + 倒排 posting, 纯 numpy 实现 (无 scipy/sklearn 依赖)
- **索引产物**: `ug_vectors.npz` (~72MB CSR+postings) + `ug_chunks_meta.json`
  (34,553 chunks), 存于 UG 根目录; 构建耗时 ~18s
- **性能**: 缓存命中后单查询 0.3–27ms
- **操作**: 构建 `python -m chip_ai_agent.ug_index build` (先 `extract` 抽 VCS
  PDF, 幂等); 检索走 MCP 工具 `chip_ug_search` 或 CLI `search <query>`;
  状态走 resource `chip://ug`

## NPI C API 检索

- **来源**: 经 `CHIP_AGENT_NPI_ROOT` 配置 — Synopsys Native Programming
  Interface, 24 个 C/C++ 头文件, 解析出 **506 个 API**
- **族谱**: npi_dm(144 设计库) / npi_fsdb(76 波形读) / npi_fsdb_trans(42) /
  npi_cov+npi_cv(29 覆盖率) / npi_util(48) / npi_nl(20 netlist) /
  npi_crdb(18) / npi_hdl(18) / npi_upf(10 低功耗) / npi_vcs(8) 等,
  另有 verdilearn (msgdb/vLLM) 接口头文件
- **实现**: `npi_index.py` 纯标准库正则解析 (声明级, 多行签名折叠), 无需预构建
- **操作**: MCP 工具 `chip_npi` (op=families/search/get) 或 CLI
  `python -m chip_ai_agent.npi_index <families|search|get>`; 总览走
  resource `chip://npi`; 环境变量 `CHIP_AGENT_NPI_INC` 覆盖头文件目录

## 黄金 UVM TB 范例库

- **来源**: 经 `CHIP_AGENT_EXAMPLE_UART` 配置 — Verification Academy
  Coverage Cookbook UART 块级环境, **89 个文件 / 12 个分类**
- **分类**: uvm_agent(31: APB/UART/modem 三agent) / uvm_env(14) /
  uvm_sequence(13) / uvm_test(9) / uvm_vsequence(8) / rtl(7) /
  uvm_tb_top(2) / uvm_regmodel / protocol_monitor / sim_script / docs
- **实现**: `examples_index.py` 纯标准库 (路径分类 + 文件名/内容检索 +
  目录穿越防护); 环境变量 `CHIP_AGENT_EXAMPLES` 覆盖根目录
- **操作**: MCP 工具 `chip_examples` (op=list/search/get) 或 CLI
  `python -m chip_ai_agent.examples_index <list|search|get>`; 总览走
  resource `chip://examples`; generate_testbench / generate_uvm_env
  recipe 可引用作黄金结构参照

## 架构

```
Claude Code ─┐               ┌─ SDK 模式: MCPServer v2 (annotations/progress/
             ├─ MCP stdio ─► │   resources/prompts/HTTP) ─ 默认
Codex ───────┤  or HTTP ──► │   mcp_server.py ─► mcp_tools.py (TOOL_DEFS 单一事实源)
VS Code ─────┘               └─ legacy 模式: 零依赖 JSON-RPC ─ 自动回退
                                    │
                          ┌─────────┴──────────┐
                     ChipAgent(plan/run)   local_tools(生成+合规+EDA)
                          │  (RLock 串行化    design_pipeline / domain_flows
                          │   写状态)         flow_guide / infra_detect
                     report_store(WAL+锁)  mcp_adapter(SDK 客户端优先, 零依赖回退)
```

**单一事实源**: 24 个工具的 name/description/schema/annotations/timeout 定义在
`mcp_tools.py::TOOL_DEFS`,同时驱动 SDK 注册 (类型签名代码生成) 与 legacy
TOOLS 列表,两份协议永不漂移。领域逻辑 (ChipAgent / local_tools / ...) 不变,
仅 `agent.py` 增加操作锁 + 逐步进度回调,`report_store.py` 增加 WAL + 线程锁
(SDK 并发调用安全)。

**客户端**: `mcp_adapter.py` 优先用 SDK v2 `Client`(持久会话, 后台 asyncio
loop),握手失败/服务器带噪音 banner/会话崩溃时自动退回原 select() 零依赖实现。

## 性能

- 工具延迟与 legacy 持平 (warm plan ~4ms; 160 技能注册表扫描单例缓存 ~40ms)。
- SDK 模式启动成本 ~0.5s (pydantic/starlette 导入栈),每客户端会话仅一次。
- streamable-HTTP 模式下服务启动即预热 agent,所有客户端首个调用即热。
- 只读工具并发安全 (registry 只读 + sqlite WAL/锁 + agent 操作锁)。
- **协议级缓存提示 (SEP-2549)**: SDK 模式对 `tools/list` / `resources/*` /
  `prompts/list` 下发 `ttl_ms=60000, scope=private` 的客户端缓存提示。
- **服务端 TTL 缓存**: SDK 模式下只读且无进度上报的工具结果按
  `(工具名, 参数)` 键缓存 (默认 30s, `CHIP_AGENT_TOOL_CACHE_TTL` 可调/关闭);
  变更型与长操作工具永不缓存。实测 (stdio 往返中位数, n=25):
  tools/list legacy 0.2ms / SDK 1.2ms;`chip_agent_skills` legacy 0.2ms /
  SDK 1.0ms — SDK 协议脚手架开销 ~1ms,缓存命中后热路径接近 legacy。

## 本轮审计与整合 (2026-10-14)

端到端 stdio 审计结论: 24 工具 + 7 静态 resources + 3 templates 全部可用。
此前审计报 ERR 的 4 项均为参数/环境误用, 非产品缺陷:

| 项 | 判定 |
|---|---|
| `chip_agent_run` intent='mux issue' isError | 预期: 无 `--server` 真实 EDA 环境时内部步骤正确报错 |
| `chip_analyze_eda_log` 无日志路径 | 预期: 缺输入时的正确错误语义 |
| `chip_check_uvm_compliance` root=/tmp | 预期: /tmp 非合规工程, 扫描误报合理 |
| template `chip://skills/verification` | 审计脚本域参数错误; 合法域取自 skill registry 实际域 (waveform/assertion/...), 用正确域读取 OK |

本轮整合改动:

1. **跨工具联动**: `flow_guide.route_intent()` 输出新增
   `assistant_tools` 字段, 按阶段 (front_end_rtl/synthesis/back_end_pd/
   signoff) 推荐辅助检索工具 (`chip_examples`/`chip_ug_search`/`chip_npi`),
   无匹配时回退 default 推荐。
2. **examples_index 进程内缓存**: 扫描结果按根目录路径缓存 (MCP server
   生命周期内), 首扫 ~4ms → 命中 ~0ms。
3. **npi families 语义标注**: verdilearn 家族 API 计数为 0 时输出
   `family_notes`, 说明其头文件使用非 npi_ 前缀命名、当前解析规则仅匹配
   `npi_*` 声明。

## 迭代优化 2 (2026-10-14, 架构路线图落地)

| Step | 优化 | 改动 | 验证 |
|---|---|---|---|
| 1 | 锁粒度 (P1) | `plan()` 去全局 op_lock (全程只读: 纯 planner + 只读 registry/memory + WAL 锁内 store 读); `ExperienceStore.add_if_new` 改为独立 RLock 保护读-改-写 (add_if_new→add 递归路径用 RLock 防死锁, 初版普通 Lock 曾被并发测试抓出死锁并修复); run() 保留 op_lock 序列化外部 MCP adapter 会话 | 8 线程 × 50 并发 add_if_new 无错误无死锁; 16 并发 plan 97ms; 125→128 passed |
| 2 | 可观测性 (P3 提前) | 新增 `metrics.py` (进程内 per-tool counters: calls/avg_ms/error_rate + SDK 缓存命中); legacy `call_tool` 与 SDK `_sdk_call` 双路径统一注入; 新 resource `chip://metrics` (10→11) | 双协议 stdio 冒烟 OK; metrics resource 快照可读 |

注: metrics 为进程本地计数 (重启归零), 定位是热路径零 I/O 的轻量观测; 如需持久化指标再引 sqlite 表。

## 迭代优化 3 (2026-10-14, mcp_tools 拆分 + 工具域标注)

| Step | 优化 | 改动 | 验证 |
|---|---|---|---|
| 3a | TOOL_DEFS 域标注 (P2) | `ToolDef` 新增 `domain: str = "general"`; 集中式 `_TOOL_DOMAINS` 映射 24 工具 → 7 域 (orchestration/verification/meta/eda/design/memory/index); legacy `tools_schema()` 输出 `domain` 键; SDK 注册 description 加 `[domain: x]` 后缀 (SDK ToolAnnotations 为严格 pydantic, 不可加自定义键) | 7 域分布 design 6 / eda 5 / index 3 / memory 3 / meta 3 / orchestration 2 / verification 2; 双协议 tools/list 均携带 domain |
| 3b | mcp_tools 拆分 (P1) | SDK codegen/缓存/`_sdk_call`/step-progress、`_make_lifespan`、resource/prompt 注册、`build_sdk_server`/`transport_config` 全部移入新 `sdk_server.py`; `_boot_audit` 留在 mcp_tools (tests 直接依赖); mcp_tools 末尾 lazy re-export + PEP 562 `__getattr__` 私有符号兼容层 (全限定 importlib 路径); `TOOL_DEFS` 保持单一事实源 | mcp_tools 1050→714 行 + sdk_server 402 行; 128 passed; py_compile 过; SDK build + list_tools=24; legacy stdio 冒烟 (initialize→tools/list domain 齐→tools/call OK) |

遗留项: ToolError(code, message, retryable) 统一错误契约 (P2, 下轮 Step 4 候选);
`CHIP_AGENT_MODE` 环境变量与文档 `CHIP_AGENT_MODE` 命名一致性复查。

## 迭代优化 4 (2026-10-14, ToolError 统一错误契约)

| 项 | 改动 | 验证 |
|---|---|---|
| ToolError 契约 (P2) | `mcp_tools.ToolError(code, message, retryable)` + `tool_error()` helper; payload 结构化 `{error, error_code, retryable}` 且保留顶层 `error` 键 (wire 向后兼容); legacy `call_tool` 未知工具→`unknown_tool`、handler 异常→`internal`(retryable=True); SDK `_sdk_call` 超时→`timeout`(retryable=True)、异常→`internal` 统一包成协议 ToolError (payload JSON) | 128 passed; py_compile 过; legacy 冒烟: unknown tool 返回 `error_code=unknown_tool`/`retryable=false`, 正常调用不受影响; 单元断言 payload/str(e) 兼容 |

错误码现状: unknown_tool / timeout / internal (域结果自身的 ok/error 语义不变, 仍由 is_error 判定)。

## 迭代优化 5 (2026-10-15, tools/list 域过滤 + config_missing)

| 项 | 改动 | 验证 |
|---|---|---|
| tools/list 域过滤 (P3) | legacy `tools_schema(domain=None)` 支持 server 端过滤; mcp_server `tools/list` 读取 `params.domain`, 未知域→显式空列表; SDK 模式维持 `[domain: x]` description 标注 (装饰器 API 不支持 per-request list 过滤) | 冒烟: domain=verification → 2 工具全 verification; 未知域 → 0; 无参 → 24 |
| config_missing 错误码 (P3) | `chip_agent_history`/`chip_agent_stats` 的 CHIP_AGENT_DB 缺失从结果体 error 升级为 `tool_error("config_missing", retryable=false)` (结构化 error_code; DB 存在时行为不变) | mock 单元验证 payload {error_code=config_missing, retryable=false} |
| 回归修复 | 昨日 18:42 signoff 门槛强制化改动后 4 个旧契约测试未同步 (裸 PASS→signoff); 按新契约修 tests: executor 需提供全部 signoff_gates 的 measured-PASS | 131 passed 全绿 |

## 迭代优化 6 (2026-10-15, tool_registry 独立切分)

| 项 | 改动 | 验证 |
|---|---|---|
| tool_registry.py (P2) | 全部 ToolDef/handler/`_TOOL_DOMAINS`/`_DEF_BY_NAME` 迁入新 `tool_registry.py` (单一事实源物理落位); registry 内 `get_agent()` lazy shim 防循环 import; mcp_tools 保留 server 管道 (dispatch/错误契约/审计/get_agent 单例) 并全量 re-export (handlers + ToolDef + TOOL_DEFS + 私有符号, 兼容 tests 与 PEP 562 层) | mcp_tools 751→260 行 / tool_registry 525 行 / sdk_server 406 行; 131 passed; py_compile 过; `TOOL_DEFS is` 同一对象 (单一事实源); 7 域 24 工具冒烟一致 |

## 迭代优化 7 (2026-10-15, 主动记忆提示 + 错误码文档化)

| 项 | 改动 | 验证 |
|---|---|---|
| recall 主动学习提示 (P3) | `chip_agent_recall` 结果新增 `distill_recommended: true` — 当目标域 experiences.jsonl 新于 knowledge.md 且记录数 ≥ AUTO_DISTILL_MIN_RECORDS(5, 与 agent 自动蒸馏同一常量) 时, 主动建议调用方执行 distill | 131 passed; 阈值与 agent.py 单一常量对齐 |
| error_code 文档化 (P3) | README 新增错误契约表 (unknown_tool/timeout/internal/config_missing + retryable) 与 Step 6 后四模块架构表、tools/list 域过滤用法 | 文档落地 |
| SDK list_tools 过滤 | 调研结论: SDK v2 装饰器 API 无 per-request list 回调, 维持 description `[domain: x]` 客户端过滤方案 (写入 INTEGRATION 记录, 非缺陷) | — |

## 迭代优化 8 (2026-10-15, 七项工程师能力矩阵落地)

| 项 | 改动 | 验证 |
|---|---|---|
| CAPABILITY_MAP | flow_guide.py 新增 7 能力条目 (理解规格/规划架构/使用 EDA 工具/阅读报告/定位根因/保护已有正确行为/PPA+物理规则收敛), 每条含 agent_mechanism 与 tools | py_compile |
| capabilities op | `chip_flow_guide {"op": "capabilities"}` 暴露能力矩阵; 错误提示含新 op | legacy MCP 冒烟: ok=true, count=7 |
| 回归测试 | test_capability_map_seven_engineer_competencies: 7 能力名精确匹配 + mechanism/tools 非空 + local tool 走线 | **132 passed** 全绿 |
| 文档 | README 新增能力矩阵表 | — |

## 迭代优化 9 (2026-10-15, 能力矩阵一致性防漂移)

| 项 | 改动 | 验证 |
|---|---|---|
| schema 同步 | chip_flow_guide ToolDef 的 op enum 增加 `capabilities`; description 显式提及能力矩阵 (legacy + SDK 共用单一事实源) | tools/list 冒烟: enum 含 capabilities |
| 防漂移测试 | test_capability_map_tools_exist_in_registry: CAPABILITY_MAP 引用的全部工具名 (含 op= 写法归一化) 必须 ∈ `_DEF_BY_NAME`; enum 同步断言 | **133 passed** 全绿 |

## 迭代优化 10 (2026-10-15, 语义级防漂移 + capabilities 只读资源)

| 项 | 改动 | 验证 |
|---|---|---|
| IR/EM 门槛缺口修复 | 语义防漂移测试发现真实漂移: 能力矩阵宣称 WNS/TNS/IR/EM/DRC/LVS/coverage, 但 pd 域 signoff_gates 缺 IR/EM (loop_back 已引用 "power/EM"); 补 `ir_drop_mv` (≤5% VDD) 与 `em_violations` (==0) 两道 measured-PASS 门槛 | 新测试逐 token 校验 gate key 存在 |
| 语义防漂移测试 | test_capability_mechanisms_grounded_in_domain_flows: 7 门槛 token→gate key 映射必须真实存在; loop_back note 引用 EM 的域必须有对应功耗类 gate | **135 passed** 全绿 |
| chip://capabilities 资源 | sdk_server 新增只读资源 `_resource_capabilities` (复用 call_local 单一事实源, 非 SDK 模式独享拷贝) | SDK 资源注册测试 + py_compile |

## 迭代优化 11 (2026-10-15, escalation/loop_back 链引用 + 域覆盖审计)

| 项 | 改动 | 验证 |
|---|---|---|
| 链引用一致性 | test_flow_internal_references_consistent: 每个 DomainFlow 的 loop_back.stage/goto、escalation.stage 必须 ∈ 本 flow stages; loop_back cap 必须为 -1 或 >0 | 15 域全过 |
| PHASES/INTENT_ROUTES 一致性 | PHASES.domains ⊆ DOMAIN_FLOWS; INTENT_ROUTES phase ∈ PHASES 且 recipe 非空; route_intent("前端 写 RTL") 端到端 = front_end_rtl | 新测试过 |
| 域标注全覆盖审计 | `_TOOL_DOMAINS` 与 `TOOL_DEFS`/`_DEF_BY_NAME` 三个集合完全相等 (无缺标/多标) | 新测试过 |

## 迭代优化 12 (2026-10-15, loop_back 方向语义 + README↔MAP 同步)

| 项 | 改动 | 验证 |
|---|---|---|
| loop_back 方向语义 | 初版方向测试抓出 17 处 "违规"; 语义分析: 就地重试 (stage→stage) 与 +1 指定修复点 (routing→timing_optimization) 为合法语义, 真正禁止的是跨 stage 前向跳转; 不变量定为 goto ≤ stage+1 | 15 域 loop_back 全合规 |
| README↔MAP 同步 | test_readme_capability_matrix_in_sync_with_map: README 能力矩阵表必须含全部 7 能力名与全部工具引用; 抓出 3 处缺失 (chip_npi/chip_agent_skills+chip_open_waveform/chip_agent_recall) 并补齐 | **140 passed** 全绿 |

## 迭代优化 13 (2026-10-15, failure_class 枚举校验 + route 歧义暴露)

| 项 | 改动 | 验证 |
|---|---|---|
| failure_class 枚举校验 | 全部 loop_back/escalation 的 failure_class 必须 ∈ FAILURE_CLASS_MAP 枚举; 每枚举 retry 策略 ∈ {none, refine, regenerate, escalate} | 新测试过 |
| route 歧义暴露 | route_intent 新增 `alternatives` (全部命中候选, 最长匹配胜出排序); 多 keyword 意图不再静默丢弃次优相位 | 冒烟: "前端 综合 都要做" → phase=front_end_rtl, alts=[(前端,…),(综合,…)] |

## 迭代优化 14 (2026-10-15, per-phase 推荐工具 + FEEDBACKS 防漂移)

| 项 | 改动 | 验证 |
|---|---|---|
| _ASSISTANT_TOOLS 校验 | 每相推荐工具 ∈ registry `_DEF_BY_NAME`; key ∈ PHASES ∪ {default}; 四相均有推荐面 (无兜底缺相) | 新测试过 (当前数据干净, 固化防回归) |
| FEEDBACKS 校验 | from_phase/to_phase ∈ PHASES; when/action 非空; 四相全部被反馈环覆盖 (含自环 fix_request 闭环) | 新测试过 |

## 迭代优化 15 (2026-10-15, checkpoint 末位门 + StageReport 枚举强制)

| 项 | 改动 | 验证 |
|---|---|---|
| checkpoint 末位审计 | 15 域 checkpoint_stage 必须 == stages[-1] (人工门在流程末端; 审计时数据全合规, 固化为契约) | 新测试过 |
| StageReport Contract #6 | failure_class 若非空必须 ∈ FAILURE_CLASS_MAP 枚举 — 修复逃逸缺口: 此前 FAIL/WARN 只要求非 none, 拼错枚举可静默绕过 retry_strategy 映射; 现有用法 (functional/timing/tool_error/none) 全部合法 | 非法值 timing_violation 被 ContractViolation 拒; **146 passed** |

## 迭代优化 16 (2026-10-15, Contract #7 — measured-PASS 必须带判据)

| 项 | 改动 | 验证 |
|---|---|---|
| Gate Contract #7 | `Gate.__post_init__`: passed=True 且 criterion 为空 → ContractViolation ("unauditable pass") — 无判据的 PASS 无法复核, 签核不可审计; NOT RUN / FAIL 不受限; gate_from_wrapper 工厂门自带 criterion 兼容 | 非法构造被拒; 4 处旧契约测试按新契约补 criterion ("== 0 (measured)") |
| 回归 | **147 passed** 全绿 (146 + 1 新增) | py_compile 过 |

## 迭代优化 17 (2026-10-15, Contract #8 — unverifiable pass 拒绝 + qor_trends JSON 模式 + NUMERIC_METRICS 对齐修复)

| 项 | 改动 | 验证 |
|---|---|---|
| Gate Contract #8 | `Gate.__post_init__`: passed=True 且 evidence 为空 → ContractViolation ("unverifiable pass") — PASS 无证据链不可信, 先于 criterion (#7) 检查执行; gate_from_wrapper 兼容 | 非法构造被拒 |
| qor_trends --json | vendored 脚本新增 JSON 模式: `{"design", "total_runs", "domains": {d: {metric: {group: [[ts, val],...]}}}}`; wrapper `digital_memory.qor_trends()` 解析为 `{"ok", "data", "output"}`, JSONDecodeError 回退纯文本, exit=1 → runs_found=0 | gpu/sta 2 条 records 真实数据端到端验证 |
| NUMERIC_METRICS 对齐修复 (P3→P1 升级) | **根因**: sta 域 trend 表缺 `wns_ns` (仅 setup/hold), 而 DOMAIN_FLOWS.sta signoff_gates 用 `wns_ns`; extract_series 返回空 series 被误报 "No runs found" (exit=1), CLI 与 JSON 模式均受影响; 修复: sta 列表补 `wns_ns` 并注释对齐来源 | CLI --json 返回 total_runs=2 完整序列 |
| 回归 | **148 passed** 全绿 (147 + 1 新增); py_compile 4 文件过; legacy 冒烟: initialize + tools/list (24) + capabilities 全通 | py_compile 过 |

## 迭代优化 18 (2026-10-15, NUMERIC_METRICS ↔ signoff_gates 全域交叉审计固化)

| 项 | 改动 | 验证 |
|---|---|---|
| 三表交叉审计 | 识别平行漂移面: qor_trends.NUMERIC_METRICS / distill.METRIC_FIELDS / DOMAIN_FLOWS.signoff_gates — Step 17 的 sta/wns_ns 缺口在其余 14 域仍有同类问题 (共 21 个数值型 gate 键不可趋势化) | 全量枚举对比 |
| NUMERIC_METRICS 全域补齐 | architecture +2, compiler +3, dft +2, firmware +1, formal +3, fpga +1, hls +1, 新增 infrastructure 行, memory-ip +1, pd +7, rtl-design +1, soc +3, sta +3, synthesis +2, verification +2 (含 lec_unmatched_points 名称对齐, 保留 lec_unmatched 兼容) | 每域数值型 gate 键全覆盖 |
| 防漂移测试固化 | `test_qor_metric_tables_cover_signoff_gates`: (1) 数值型 signoff gate 键 (单位/计数后缀 + 特例表) ⊆ NUMERIC_METRICS[domain]; (2) distill.METRIC_FIELDS ⊆ NUMERIC_METRICS (路径加载 vendored 模块) — 新增 gate 键漏配趋势表即红 | 抓出并修复 vmin_margin_mv 漏配 (测试先红后绿) |
| 回归 | **149 passed** 全绿 (148+1 新增); py_compile 过; legacy 冒烟含 chip_qor_trends MCP 调用端到端 (total_runs=2) | py_compile 过 |

## 迭代优化 19 (2026-10-15, 工具域命名空间 ↔ 工程域命名空间交叉审计)

| 项 | 改动 | 验证 |
|---|---|---|
| 域表一致性修复 | 发现 qor_trends.VALID_DOMAINS (14 域) 缺 `infrastructure` — 与 DOMAIN_FLOWS (15 域) / distill.VALID 漂移; 补齐后三表逐名一致 | 新测试锁定 |
| domain 参数 enum 单一事实源 | tool_registry 新增 `DOMAIN_ENUM = sorted(DOMAIN_FLOWS)`; chip_memory_search / chip_memory_distill / chip_agent_recall / chip_qor_trends 四个 domain 参数从自由字符串改为 enum 绑定 — 禁止私有枚举漂移 | schema 校验由 SDK/客户端共同生效 |
| 能力域→工程域覆盖矩阵 | 审计结论: _TOOL_DOMAINS (7 能力域: orchestration/verification/meta/eda/design/memory/index) 是客户端过滤命名空间, DOMAIN_FLOWS (15 工程域) 是流程命名空间 — 二者职责不同但必须覆盖闭环: design 覆盖 14 工程域, verification 覆盖 verification, memory 覆盖全域; 新测试固化覆盖矩阵 + 全工具域标注完整性 | 新测试过 |
| 回归 | **150 passed** 全绿 (149+1 新增); py_compile 过; legacy 冒烟: domain 过滤 tools/list (verification→2 工具) + chip_qor_trends 端到端 | py_compile 过 |

## 迭代优化 20 (2026-10-15, PHASES ↔ DOMAIN_FLOWS ↔ NUMERIC_METRICS 相位级交叉审计)

| 项 | 改动 | 验证 |
|---|---|---|
| 相位 gate 单位对齐 | back_end_pd 相位 gate `hold_wns_ns` → `hold_wns_ps` — pd 域权威 (signoff_gates) 用 ps 单位, 相位聚合视图不得发明新键/新单位 | 审计先红后绿 |
| signoff 相位域补齐 | signoff.domains 增加 `pd` — 物理验证 (DRC/LVS/ANT) 属 pd 引擎; 此前 signoff 相位 gate 含 drc_violations/lvs_errors 但域集合不含 pd, gate 无所属引擎 | chip_flow_guide phase=signoff 端到端确认 |
| 相位级防漂移测试固化 | `test_phase_namespace_cross_audit`: (1) PHASES.domains ⊆ DOMAIN_FLOWS; (2) 数值型相位 gate 键 ⊆ 该相位域集 signoff_gates 并集 (聚合视图不发明键); (3) ⊆ NUMERIC_METRICS 并集 (可趋势化) | 新测试过 |
| 回归 | **151 passed** 全绿 (150+1 新增); py_compile 过; legacy 冒烟 signoff/back_end_pd 相位详情全通 | py_compile 过 |

## 迭代优化 21 (2026-10-15, INTENT_ROUTES ↔ PHASES ↔ RECIPES 路由表交叉审计)

| 项 | 改动 | 验证 |
|---|---|---|
| 路由表全量审计 | 47 条 INTENT_ROUTES: phase 全部 ∈ PHASES, recipe 全部 ∈ RECIPES, 无重复关键词, 每相位路由数 front_end_rtl=13 / synthesis=7 / back_end_pd=12 / signoff=10 (无盲相), fallback design_onboarding 存在 — 审计数据干净 | 全量枚举 |
| 防漂移测试固化 | `test_intent_route_table_audit`: 路由不得指向幽灵 phase/recipe; 重复关键词会静默破坏最长匹配胜出语义 (直接红); 每相位 ≥3 关键词; fallback recipe 必须存在 | 新测试过 |
| 回归 | **152 passed** 全绿 (151+1 新增); py_compile 过; 冒烟: route_intent("tapeout")→signoff/signoff_tapeout (alternatives 2 条) + 未命中→design_onboarding + legacy MCP op=route 端到端 | py_compile 过 |

## 迭代优化 22 (2026-10-15, 运行时 gate 命名 taxonomy 审计)

| 项 | 改动 | 验证 |
|---|---|---|
| 疑点排除 | Step 22 初判的 `_normalize` 丢 `inferred` 字段为行号偏移错觉 — design_pipeline.py:143 已正确传递 `inferred=g.get("inferred", False)`, 无 bug | 直接读源码 + 既有 inferred 测试过 |
| gate 命名诊断 | `_signoff_gate` 新增 taxonomy 诊断: executor 报告的 gate 未命中 signoff 门时, 区分 (a) 方向性单位后缀近失配 ('wns' ≈ 'wns_ns' → 提示 rename), (b) 中间/wrapper 未匹配 gate ('gate_0'、非 `wrapper:` 前缀的杂名) — fail-closed 语义不变, 仅把静默 unmeasured 升级为可定位根因提示 | 新测试过 |
| 方向性匹配设计 | `_gate_variants(expected)`: 接受集 = 精确名 + 去单位后缀变体; reported 名永不剥离自身后缀, 避免 'drc_violations' 撞 'ns' 词干的全局规范化歧义 | 单元测试 `_norm_gate`/`_gate_variants` 固化 |
| 测试固化 | 3 个新测试: `test_domain_flow_gate_name_mismatch_diagnosed` (错名 fail-closed + reason 含 rename 提示), `test_domain_flow_intermediate_gate_does_not_block_signoff` (中间 gate 不阻塞 signoff), `test_gate_taxonomy_diagnostics_unit` | 新测试过 |
| 回归 | **215 passed** 全绿; py_compile 过; legacy MCP 冒烟 init+tools/list=24 | py_compile 过 |

## 迭代优化 23 (2026-10-15, route_intent 运行时闭合 + wrapper 门命名空间统一)

| 项 | 改动 | 验证 |
|---|---|---|
| route_intent 运行时闭合 (Step 14 遗留收口) | `test_route_intent_closure_all_routes`: 全部去重关键词 (最长优先) 逐条走 route_intent, phase/recipe 必须复现 INTENT_ROUTES 表项, assistant_tools ⊆ registry `_DEF_BY_NAME`, 四相全路由可达 | 新测试过 |
| wrapper 门命名空间统一 (真 gap 修复) | `gate_from_wrapper` 生成裸名 (如 `sta_report`) 与 design_pipeline taxonomy 审计豁免的 `wrapper:` 前缀命名空间不一致 → 现统一为 `wrapper:<tool>` (无名时 `wrapper:unnamed`) | `test_gate_from_wrapper_uses_wrapper_namespace` 过; 2 处旧测试只断言 passed 不受影响 |
| Reporting 契约全景表 | Contract #1–#8 (#1 wrapper verified / #2 NOT RUN / #3 measured-vs-inference / #4 failure_class / #5 signoff 全门 measured-PASS / #6 taxonomy 枚举 / #7 criterion / #8 evidence) 写入 INTEGRATION.md 顶部 | 文档与 reporting.py 源码逐条核对 |
| 回归 | **162 passed** 全绿 (+2); py_compile 过; legacy MCP 冒烟 (沿用 Step 22 基线) | py_compile 过 |

## 迭代优化 24 (2026-10-15, post-RTL 深度签核清单 ↔ 域门硬映射)

| 项 | 改动 | 验证 |
|---|---|---|
| 用户工业要求结构化 | `POST_RTL_CHECKLIST` 7 项 (flow_guide.py): 综合前后 LEC / GL+post-route 功能 / SDC&时钟约束 / setup-hold 闭合 / reset-CDC-低功耗-X 传播 / ECO 等价 / PPA 回归保护 — 每项含 why + domains + gates + agent_check + tools | 新测试过 |
| 与执行引擎硬绑定 | 审计测试强制每个清单 gate ⊆ 对应 DOMAIN_FLOWS[domain].signoff_gates (防"清单与引擎脱节"); tools ⊆ registry; 7 项 id 唯一 | `test_post_rtl_checklist_gates_map_to_real_domain_gates` 过 |
| MCP 暴露 | chip_flow_guide 新增 `op=post_rtl_checklist` (enum + local_tools 分发 + 描述更新) | `test_flow_guide_post_rtl_checklist_op` + legacy MCP tools/call 端到端过 (7 项返回) |
| 回归 | **164 passed** 全绿 (+2); py_compile 过; legacy 冒烟 tools=24, enum/调用均过 | py_compile 过 |

## 迭代优化 25 (2026-10-15, ToolError 契约全局审计后收口)

| 项 | 审计发现 → 修正 | 验证 |
|---|---|---|
| 审计先行 | 全库审计两分发点+local_tools+registry: A1 ToolError/tool_error **已存在** (legacy unknown_tool/异常, SDK 异常/timeout 已用) — 交接摘要过期, 避免重复造轮 | 全局 grep+读码 |
| A2 应用级错误无契约 | `d.is_error(res)` 结果现在统一包 `_app_error_envelope` = {error, error_code:"tool_reported_error", retryable:false, result:原payload} — legacy call_tool 与 SDK _sdk_call 两点一致, 人读信息零丢失 (result 保留) | `test_tool_error_contract_application_errors` 过 (双模式) |
| A3 legacy 忽略 timeout | `_run_handler_with_timeout`: daemon 线程 + join(timeout), 超时返回 `timeout`/retryable=true 信封; 语义与 SDK 一致 ("后台可能仍在跑"); 实现教训: ThreadPoolExecutor with 退出会 join worker 反而挂死 — 改 daemon Thread | `test_legacy_call_tool_enforces_timeout` 过 (5s 任务 0.05s 返回) |
| A4 metrics 丢时长 | `_t0` 提到 try 外, ToolError/timeout/异常路径均记真实 duration | 代码审 + 回归 |
| 回归 | **172 passed** 全绿 (+3); py_compile 过; legacy MCP 端到端: bogus op→tool_reported_error 信封, 未知工具→unknown_tool 信封 | py_compile 过 |


## 迭代优化 28 —— 全局剔除开源 EDA 工具（仅 Synopsys / Cadence / Siemens）

| 审计面 (S1–S7) | 修正内容 | 状态 |
|---|---|---|
| S1 运行时 import | `eda_wrappers.py` 删除；`mcp_tools.py`/`agent.py`/`tool_registry.py`/`local_tools` 残留 import 清零 | ✅ |
| S2 工具注册表 | `chip_eda_wrappers` ToolDef + domain tag 移除；工具总数 24→23 | ✅ |
| S3 领域流 (15 域) | `tools_oss/tools_proprietary` → `tools_synopsys/tools_cadence/tools_siemens/tools_utilities` + `vendor_tool` | ✅ |
| S4 流程指南 | 4 相统一 vendor dict；CAPABILITY_MAP 去 wrapper | ✅ |
| S5 基础设施探测 | `infra_detect` 重写：22 vendor 工具 + 非EDA utilities；`open_source_eda_policy="removed by directive"` | ✅ |
| S6 recipes / pipeline | `list_eda_wrappers` 步骤删除；HLS 前工具映射至 catapult/stratus；`vendor_tool` 优先 | ✅ |
| S7 测试防线 | 新增 22 名单零回流扫描（排除 vendored `digital/plugins/**` 参考物）+ vendor 路由审计 + infra 三厂商探测；旧 wrapper 测试删除 | ✅ |
| HTML 审计 | `platform/static/index.html`、`frontend/index.html` 零 EDA 引用（LSF 平台前端），无需修正 | ✅ |

**回归**：`pytest tests -q` → **187 passed**；py_compile 全部改动文件 OK；legacy MCP 冒烟 init+tools/list=23（无 chip_eda_wrappers），chip_infra_detect 返回三 vendors（detect-only，never auto-install/license）。

**注**：历史迭代记录中的 OSS 工具表述按原文保留（历史记录不篡改），现行为以本轮及代码为准。wrapper 层伪签核防御职责随 OSS 移除转为 vendor 日志解析（`eda_log_analyzer` 路径）。

## 迭代优化 29 —— eda_log_analyzer 三厂商日志解析全覆盖

| 项 | 内容 | 状态 |
|---|---|---|
| 审计 | 文档（README/CHIP_FLOW_GUIDE/DATA_REQUIREMENTS）OSS 词零残留；eda_log_analyzer 原仅覆盖 vcs/verdi/lsf | ✅ |
| 新增解析器 | xcelium（*E,SEVFX + Errors/Warnings 摘要）、questa（# \*\* Error/Fatal）、genus（*Error,MSGID RC 族）、innovus（\*\*ERROR:）、calibre（ERROR:/WARNING: + Total Results） | ✅ |
| 检测优先级 | vendor 专属标记前置，generic bare-"Error:" 兜底后置，避免 Questa/Calibre/Innovus 误路由 vcs_compile | ✅ |
| recipe 路由 | xcelium→simulation_run、questa→uvm_verification_flow、genus→logic_synthesis_flow、innovus→physical_design_flow、calibre→signoff_tapeout；新增 kind 级默认路由兜底 | ✅ |
| 零回流修正 | INTEGRATION.md 28 节 HLS 前工具字面量改写（ catapult/stratus 对齐） | ✅ |

**回归**：`pytest tests -q` → **189 passed**（新增 2 个三厂商解析测试）；py_compile OK；legacy MCP 冒烟 tools/list=23，chip_analyze_eda_log 可调用。

## 迭代优化 30 —— 三厂商跨模块一致性防线

| 审计面 | 结果 | 状态 |
|---|---|---|
| `eda_tools.py` 运行时桥 | 站点 Synopsys 套件专用（vcs/verdi/NPI/UVM），零 OSS 引用，degraded 时携带 `module load` setup | ✅ |
| `chip_edatools` MCP 暴露 | 正确复用 `infra_detect.detect_tools()`，三 vendors + detect-only 政策 | ✅ |
| `npi_tools.py` | 零 OSS 引用 | ✅ |
| 新增防线 `tests/test_vendor_consistency.py` | ① 22 产品 × 三厂商清单锁定 ② eda_tools 工具集 ⊆ Synopsys 产品清单 ③ 日志解析 kind ↔ 产品映射 ④ chip_edatools 输出结构契约 ⑤ 12 个运行时源文件词边界 OSS 扫描 | ✅ |
| 测试自身修正 | 误加 "wired" 名单项移除；"vlog" 类子串误报改 `\b` 词边界匹配；vcs 解析 kind 修正为 vcs_compile/vcs_uvm_sim | ✅ |

**回归**：`pytest tests -q` → **194 passed**（新增 5 个一致性测试）；py_compile OK。

## 迭代优化 31 —— UG 技术手册按"章节 / 操作步骤"切分单元

| 项 | 内容 | 状态 |
|---|---|---|
| 切分模型 | 固定 1200 字符滑窗 → 结构感知：`_chunks_structured()` 以章节标题（Chapter N / Section N / N.N 子节 / N 顶层节）与操作步骤块（Step N / N. / a.）为切分单元；CHUNK_CHARS 降级为打包上限 | ✅ |
| 元数据 | chunk 携带 `section`（所属章节标题）+ `kind`（chapter/steps/prose）；search 命中结果同步返回 | ✅ |
| 切分精度修正 | 步骤 `N.` 与编号标题冲突（`\d\.?\s+[A-Z]`）→ 多级编号必须含点分数字；短标题章节保底产出 1 个单元（标题即高价值检索上下文）；闭包晚绑定修复 | ✅ |
| 真实索引重建 | /tools/Synopsys/temp/ug：128 docs → **34574 chunks**（steps 19915 / prose 10749 / chapter 3910；带标题 4000），16.5s | ✅ |
| 测试 | 新增 2 个：切分单元结构断言（步骤列表完整、单元携带章节标题）+ meta/hits 字段契约 | ✅ |

**回归**：`pytest tests -q` → **196 passed**；py_compile OK；MCP 冒烟 chip_ug_search 命中返回 kind/section 字段。

## 迭代优化 32 —— chip_ug_search kind 过滤 + 文档残留复核

| 项 | 内容 | 状态 |
|---|---|---|
| kind 过滤 | `ug_index.search(kind=...)` 只命中 chapter/steps/prose 指定单元；handler + ToolDef schema enum 同步 | ✅ |
| ToolDef 描述 | 更新为"章节/操作步骤切分单元 + section/kind 出处"，暴露 kind=steps 用法 | ✅ |
| 文档残留复核 | README/CHIP_FLOW_GUIDE 全文扫描：OSS 工具词零残留（唯一命中为 CrossDomain 中 "oss" 子串误报） | ✅ |
| 测试 | 新增 kind 过滤契约测试（prose 命中即 kind 一致；steps 过滤空结果） | ✅ |

**回归**：`pytest tests -q` → **197 passed**；py_compile OK；MCP 冒烟：真实索引 kind=steps 查询仅返回步骤单元。

## 迭代优化 33 —— 失败 EDA log 自动附 UG 手册步骤级指引

| 项 | 内容 | 状态 |
|---|---|---|
| 查询生成 | `eda_log_analyzer.ug_step_queries(kind, failure_class)`：按 9 类 log kind（vcs编译/UVM/Verdi/Xcelium/Questa/Genus/Innovus/Calibre/LSF）+ 失败分类生成 1-2 个 UG 检索词（如 genus+timing→"Genus synthesis flow"+"timing constraints setup hold"） | ✅ |
| 工具接线 | `local_tools.analyze_eda_log`：verdict ∉ {PASS, UNKNOWN} 且索引已建时，逐查询 `ug_index.search(q, kind="steps", top_k=3)` → `res["manual_steps"]`；索引缺失/异常优雅降级（note，不报错） | ✅ |
| 依赖可选 | 手册指引不影响分析主链路：索引未建 = 无 manual_steps 字段；PASS 结果永不附带 | ✅ |
| ToolDef 描述 | chip_analyze_eda_log 更新为"三厂商全kind + 失败时自动附 UG 手册步骤级指引" | ✅ |
| 测试 | 新增 4 个：查询生成映射、FAIL 附 manual_steps（kind==steps）、索引缺失降级、PASS 不附带 | ✅ |

**回归**：`pytest tests -q` → **201 passed**；py_compile OK；legacy MCP 冒烟：tools=23，Genus 失败日志经 chip_analyze_eda_log 返回 FAIL + manual_steps（命中真实索引 steps 单元）。

## 迭代优化 34 — DVCon 2025/2026 论文语料索引 + chip_dvcon_search MCP 工具

| 项目 | 内容 | 状态 |
|---|---|---|
| 联网检索 | dvcon-proceedings.org Proceedings Archive + dvcon.org 2025/2026 technical sessions，真实论文条目 | ✅ |
| 种子语料 | `dvcon_seed_corpus.json`：28 篇（2025×15 + 2026×13），含 Samsung/Infineon/Nvidia/Siemens/Cadence/Synopsys 等真实标题与作者/机构 | ✅ |
| 新模块 | `dvcon_index.py`：切分单元 abstract(种子)/method(方法描述标记)/conclusion(结论/未来工作标记)/paragraph；复用 ug_index blake2 哈希 TF-IDF 倒排（独立 DIM=2^16 + 独立缓存）；支持用户放置 .md/.txt/.pdf 全文扩语料（pypdf） | ✅ |
| 检索 API | `search(query, year=, kind=, top_k=)`；索引缺失时自动用种子语料建库；`status()` 输出 kind/year 分布 | ✅ |
| MCP 工具 | `chip_dvcon_search`（readOnly，year/kind enum 过滤，top_k≤20），TOOL_DEFS 23→**24**，双模式（SDK/legacy）共用单源 | ✅ |
| 全局审计 | 5 处测试断言 23→24 同步（mcp_sdk_mode×2 + ro 集合、npi、examples、ug_index）；OSS 词回流扫描通过；三厂商政策不变 | ✅ |
| 验证链 | pytest **205 passed**；py_compile OK；legacy MCP 冒烟 tools=24，chip_dvcon_search 检索命中 2026 agentic regression 论文 | ✅ |
| CLI | `python -m chip_ai_agent.dvcon_index build/search/status`（--year/--kind/--top-k） | ✅ |

## 迭代优化 35 — EDA日志↔DVCon论文跨域闭环 + 主动记忆/主动学习增强

| 项目 | 内容 | 状态 |
|---|---|---|
| 全局审计 | 基线 205 passed / tools=24 / OSS 零回流；定位 5 处相关模块（eda_log_analyzer、local_tools、dvcon_index、tool_registry、tests）后统一修正 | ✅ |
| 跨域闭环 | `eda_log_analyzer.dvcon_queries(kind, failure_class)`：9 类失败分类→论文检索词映射 | ✅ |
| 论文方法推荐 | `chip_analyze_eda_log` 失败时输出 `dvcon_methods`（每类失败附 1-2 组 ×2 篇论文 title/authors/year/excerpt）；verdict=UNKNOWN 但已分类的运行也纳入（此前被跳过，属 debug 修复）；优雅降级 | ✅ |
| 主动记忆 | `dvcon_index.digest()`：语料蒸馏为 `dvcon_knowledge.md`（按年份、幂等确定性、语料变化重跑即更新） | ✅ |
| 主动注入 | `chip_agent_recall` 对 verification 相关 intent 自动注入 `dvcon_trends_preview`（蒸馏摘要前 900 字），best-effort 不破坏 recall | ✅ |
| 测试 | 新增 5 测试（queries 映射/analyze 联动/digest/recall 注入/relevance+filter 复验）；修 fixture 假种子覆盖真语料缺陷 | ✅ |
| 验证链 | pytest **206 passed**；py_compile OK；legacy MCP 冒烟 tools=24，recall 含 dvcon_trends_preview | ✅ |

## 迭代优化 36 — 论文推荐持久学习 + failure_class 直查

| 项目 | 内容 | 状态 |
|---|---|---|
| 持久学习 (P1) | `chip_analyze_eda_log` 新增 opt-in `learn` 参数：dvcon_methods 命中后 upsert 到 DomainMemory("verification")（run_id=`dvcon-methods-<failure_class>`，fixes_applied=论文标题），同类失败下次由记忆直接召回，不再重搜语料 | ✅ |
| readOnly 语义 | learn 默认关闭，`chip_analyze_eda_log` 保持 readOnlyHint 语义不变 | ✅ |
| failure_class 直查 (P2) | `chip_dvcon_search` 支持 `failure_class` 入参（query 变为可选）：经 `dvcon_queries` 映射后检索；两者都缺返回明确 error | ✅ |
| 冒烟 | `chip_dvcon_search{failure_class:"spec_gap"}` → 命中 "AI Agent-based Specification Matching System for SoC RTL Verification" 等 | ✅ |
| 验证链 | pytest **207 passed**（新增 1）· py_compile OK · OSS 零回流 · legacy MCP tools=24 · INTEGRATION.md | ✅ |

## 迭代优化 37 — 论文 track tags + post_rtl_checklist ↔ DVCon 双向链接

| 项目 | 内容 | 状态 |
|---|---|---|
| track tags | `dvcon_index.tags_for()` 关键词自动标注 7 类 track（ai/verification/low-power/cdc/timing/signoff/stimulus），无需手工标注；索引 meta 增加 tags，重建 30 chunks（28 种子+2 全文段） | ✅ |
| tag 过滤 | `chip_dvcon_search` 新增 `tag` enum 入参；CLI `--tag`；hits 携带 tags 出处 | ✅ |
| checklist 联动 | `chip_flow_guide.post_rtl_checklist` 7 项检查项按 id 映射检索词，自动附 `dvcon_papers`（title/authors/year/query），best-effort 降级 | ✅ |
| 冒烟 | tag=low-power → "UPF 4.0: Power Intent for the AI Era"；checklist 7/7 项带论文链接 | ✅ |
| 验证链 | pytest **208 passed**（新增 1）· py_compile OK · OSS 零回流 · legacy MCP tools=24 · INTEGRATION.md | ✅ |

## 迭代优化 39 — HTML 语料导出转换 (PCIe OVM SFT)

| 项 | 说明 | 结果 |
|---|---|---|
| 工具包安装 | `.venv` pip 安装 beautifulsoup4 4.15.0 + lxml（HTML 解析） | ✅ |
| 新模块 | `chip_ai_agent/corpus_convert.py`：解析导出 HTML 内嵌 `const CORPUS` JS 数组，容错截断记录 | ✅ |
| 语料输出 | `chip_ai_agent/corpus/pcie_ovm/`：sft.jsonl / sft.json / alpaca.json / sharegpt.json + manifest.json | ✅ 23 条，JSONL 全量回验通过 |
| 内容域 | Synopsys PCIe OVM VIP（agent 配置 / 复位序列 / 覆盖率回调 / TLP-DLLP / LTSSM） | ✅ 三厂商政策合规（OSS 词零命中） |

## 迭代优化 39b — 厂商手册→Agent 领域技能全链路 (PCIe OVM UG)

| 阶段 | 实现 | 结果 |
|---|---|---|
| ① 提取+切分 | `pcie_index.py`: pypdf 提取 359 页 → chapter/heading/steps/code 结构化单元 + hashed tf-idf 向量索引 (复用 ug_index) | ✅ 115 单元 (steps 15 / code 19 / prose 81) |
| ② SFT 语料 | `generate_sft()`: 单元→Alpaca QA 启发式生成, 与 23 条 curated 合并去重 | ✅ 90 条 pcie_ovm_sft.jsonl |
| ③ LoRA | `training/pcie_ovm/train_lora_unsloth.py` (Qwen2.5-Coder + Unsloth, 4bit, GGUF 导出) | ✅ 脚本就绪 (torch 栈按需安装) |
| ④ Ollama | `Modelfile.pcie-ovm` + `training/pcie_ovm/README.md` (create pcie-ovm → :11434/v1) | ✅ 就绪 |
| ⑤ FastMCP Tool | `fastmcp_pcie_server.py`: search_pcie_guide + generate_pcie_config (mcp 1.x/2.x 双兼容) | ✅ stdio 端到端冒烟通过 (list_tools=2, call_tool 成功) |
| ⑥ Agent 接入 | `skills/pcie_ovm_guide/SKILL.md` 领域技能 (检索优先、引用章节、代码仅来自 code 单元) | ✅ 全量回归 209 passed |

## 迭代优化 39c — DVCon 2025/2026 论文再搜索 → SFT 语料转化

| 项 | 说明 | 结果 |
|---|---|---|
| 再搜索 | dvcon.org 官方技术程序全量抓取: 2025×60 + 2026×58, 与 28 条旧 seed 仅 6 条重叠 | ✅ |
| 种子库扩充 | 118 条官方条目按 title 归一去重合并 (3 条跨 session 重复), 真实作者全名回填 8 条, 补充 session 字段 | ✅ 28→**137 篇** (2025×73 / 2026×64) |
| 向量索引 | digest→build 重建, hashed tf-idf | ✅ 30→**144 chunks** (abstract 137 / method 7) |
| SFT 语料 | `dvcon_index.generate_sft()`: curated 3 + seed 137 + fulltext unit 1, Alpaca JSONL | ✅ **141 条** `corpus/dvcon/dvcon_sft.jsonl` |
| FastMCP | `fastmcp_dvcon_server.py`: search_dvcon_papers + propose_verification_methodology (mcp 1.x/2.x 双兼容) | ✅ stdio 端到端冒烟 (list=2, 检索/提案均命中真实论文) |
| 技能 | `skills/dvcon_papers/SKILL.md` (When To Use / Data Assets / Method / Pitfalls) | ✅ |
| manifest | `corpus/dvcon/manifest.json` (SHA-256) | ✅ |
| 全局审计 | pytest **215 passed** (新增 1) · py_compile OK · legacy MCP tools=24 · OSS 零回流 (8 个新增/修改面扫描) | ✅ |
