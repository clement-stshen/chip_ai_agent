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

**SDK 来源 (provenance)**: 默认安装 `/tools/Synopsys/temp/python-sdk`
官方源码树 (git rev `754254c0`,版本 `mcp 2.3.1.dev9+754254c0` +
同源 `mcp-types`)。monorepo 内部 `mcp-types` 需与 `mcp` 同 checkout 安装
(`install_sdk.sh` 已处理);PyPI 回退路径为 `mcp==2.3.0`。

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
| `chip_eda_wrappers` | 列出/运行 8 个输出压缩 EDA wrapper (大日志→紧凑JSON, exit 0≠pass) | |
| `chip_design_pipeline` | spec→tape-out 引擎: plan/status/run/next/re_verify (域内 loop-back + 跨域闭环 + checkpoint 门) | |
| `chip_domain_flows` | 15 域机器可读流程查询 (阶段/loop-back 上限/sign-off 门/工具路由) | ✔ |
| `chip_infra_detect` | 基础设施检测: 24 开源 + 7 商用(detect-only) + wrapper/MCP 部署状态 | ✔ |
| `chip_flow_guide` | 四相芯片研发流程 (前端RTL→综合→后端→Signoff); route 按 intent 定位 | ✔ |
| `chip_ug_search` | VCS+Verdi 官方 UG 手册向量检索 (哈希TF-IDF, 128 docs/34.5k chunks); 附 product/doc/chunk 出处 | ✔ |
| `chip_npi` | Synopsys NPI C API 检索: 24 头文件/506 API (FSDB/覆盖率/UPF/VCS/NL/VerdiLearn); families/search/get | ✔ |
| `chip_examples` | 黄金 UVM TB 范例库 (uart_example: APB/UART/modem 三agent, 89 文件12类); list/search/get | ✔ |

只读工具标注 `readOnlyHint=true, destructiveHint=false`,客户端可安全并行调用。
所有工具 `destructiveHint=false` (该工具面不删除任何用户数据)。
长操作 (`chip_agent_run` 逐步 / `chip_run_simulation` / `chip_eda_wrappers` /
`chip_memory_distill` / `chip_qor_trends` / `chip_check_uvm_compliance`) 通过
MCP progress 通知实时上报进度。

## Resources (7 个, SDK 模式)

| URI | 内容 |
|---|---|
| `chip://skills` | 全部 153 个技能与领域分布 (含 uvm_methodology) |
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

服务端启动时预热 agent 单例 (153 技能注册表扫描), 所有客户端首个调用即热。
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

- **来源**: `/tools/Synopsys/temp/ug` (VCS + Verdi Y-2026.03-SP1), 128 篇文档
- **方案**: 段落切分 (~1200 字符带重叠) → 哈希 TF-IDF 稀疏向量 (word 1-2 gram,
  dim=2^18, L2 归一化) + 倒排 posting, 纯 numpy 实现 (无 scipy/sklearn 依赖)
- **索引产物**: `ug_vectors.npz` (~72MB CSR+postings) + `ug_chunks_meta.json`
  (34,553 chunks), 存于 UG 根目录; 构建耗时 ~18s
- **性能**: 缓存命中后单查询 0.3–27ms
- **操作**: 构建 `python -m chip_ai_agent.ug_index build` (先 `extract` 抽 VCS
  PDF, 幂等); 检索走 MCP 工具 `chip_ug_search` 或 CLI `search <query>`;
  状态走 resource `chip://ug`

## NPI C API 检索

- **来源**: `/tools/Synopsys/temp/NPI/inc` — Synopsys Native Programming
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

- **来源**: `/tools/Synopsys/temp/uart_example` — Verification Academy
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

- 工具延迟与 legacy 持平 (warm plan ~4ms; 153 技能注册表扫描单例缓存 ~40ms)。
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
