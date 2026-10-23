# chip_ai_agent 安装 / 配置 / 使用手册

> 配套文档: [FEATURES.md](FEATURES.md) · 版本 2.0.0 · 2026-10

## 1. 快速安装(在线)

```bash
# ① MCP SDK v2 (装入共享 venv; 不装则自动退回零依赖 legacy 模式)
bash chip_ai_agent/install_sdk.sh              # 本地源码构建
bash chip_ai_agent/install_sdk.sh --pypi       # 或 PyPI 发布版 mcp==2.3.0

# ② 注册 Claude Code + Codex + 安装 14 个方法论技能 (幂等)
bash chip_ai_agent/install_integration.sh
```

完成后在 `claude` 交互应用内**一次性批准**项目 MCP 服务器
(chip-agent / verif-agent),此后永久生效。

## 2. 离线安装(全部依赖已本地化)

依赖 wheel 已下载至 `chip_ai_agent/wheelhouse/`(**47 wheels**:
mcp 2.3.0 + mcp-types + numpy + pypdf + pytest + beautifulsoup4 + fonttools
及全部传递依赖;scratch venv `--no-index` 实测通过):

> **完全离线审计结论 (2026-10 复核)**: ① pip 层闭包全覆盖 — 全代码库
> 第三方 import 仅 mcp/anyio/numpy/pypdf/bs4(+fonttools 软依赖)+ 站点
> pynpi,全部有 wheel 或随包; ② 零依赖 legacy 启动链验证 — 屏蔽 numpy
> 后 initialize+tools/list=24 正常 (numpy 仅语料工具按需加载); ③ 随包
> 数据 (skills/digital/dvcon 索引/设计状态) 自包含; ④ 站点数据 (NPI/UVM/
> UG/uart/uvm_tb) 由 `bundle_offline.sh` 一并打包, 缺失时对应工具按契约
> 优雅降级, 核心验证流 (plan/generate/check/memory) 零外部数据可运行。

```bash
# 环境变量: CHIP_AGENT_WHEELHOUSE(默认 chip_ai_agent/wheelhouse)、
# CHIP_AGENT_PYTHON(默认站点值见 site_paths.py)
"$CHIP_AGENT_PYTHON" -m pip install --no-index --find-links "$CHIP_AGENT_WHEELHOUSE" \
    "mcp==2.3.0" "mcp-types==2.3.0" numpy pypdf pytest beautifulsoup4 fonttools
# 或: bash chip_ai_agent/install_offline.sh

# 整包打包 (代码+wheelhouse+模板+站点数据, 目标机解包即部署):
bash chip_ai_agent/bundle_offline.sh [输出 tar 路径]
```

站点数据依赖(非 pip,路径均 env 可配):NPI kit、UVM 库、UG 手册语料、
UART 范例树 — 见第 4 节变量表。

## 3. 客户端配置

### Claude Code
```bash
# 推荐用 venv python(带 numpy/MCP SDK, 语料检索完整);
# 或: bash chip_ai_agent/install_integration.sh 自动完成
claude mcp add chip-agent -s user -- "$CHIP_AGENT_PYTHON" "$CHIP_AGENT_HOME/mcp_server.py"
claude mcp list     # ✔ Connected
```
项目级(随工程分发): `${CHIP_AGENT_HOME}/../.mcp.json`(含 chip-agent + verif-agent
两个 server 及 env)。

### Codex
`~/.codex/config.toml`:
```toml
[mcp_servers.chip_agent]
command = "<CHIP_AGENT_PYTHON>"
args = ["<CHIP_AGENT_HOME>/mcp_server.py"]
```

### 团队共享(HTTP)
```bash
CHIP_AGENT_TRANSPORT=streamable-http CHIP_AGENT_PORT=8000 \
  python3 chip_ai_agent/mcp_server.py
claude mcp add chip-agent-http --transport http http://127.0.0.1:8000/mcp
```

## 4. 配置变量总表

### 4.1 站点路径(全部 env 可覆盖,默认保持现址)
| 变量 | 默认值 |
|---|---|
| `CHIP_AGENT_TEMPLATE_TB` | UVM 模板工程 (默认站点值) |
| `CHIP_AGENT_MODULEFILES` | :分隔 modulefile 路径 |
| `CHIP_AGENT_EDA_ROOTS` | :分隔 EDA 厂商根 |
| `CHIP_AGENT_NPI_ROOT` | NPI kit (默认站点值) |
| `CHIP_AGENT_UVM_ROOT` / `_TGZ_ROOT` | UVM 库 / tarball 父目录 |
| `CHIP_AGENT_UG_ROOT` / `_DVCON_ROOT` | 语料根 |
| `CHIP_AGENT_EXAMPLE_UART` | UART 范例树 |
| `CHIP_AGENT_VERIF_AGENT_BIN` / `_CONFIG` | verif-agent 可执行/config |

### 4.2 运行时与学习
| 变量 | 作用 |
|---|---|
| `CHIP_AGENT_MODE` | auto(默认)/ sdk / legacy |
| `CHIP_AGENT_TRANSPORT` | stdio(默认)/ streamable-http |
| `CHIP_AGENT_HOST/PORT/STATELESS` | HTTP 绑定 |
| `CHIP_AGENT_SKILLS` / `_EXTRA_SKILLS` | 技能目录 |
| `CHIP_AGENT_DB` / `_EXPERIENCE` | 运行库 / 经验文件 |
| `CHIP_DESIGN_STATE` / `_MEMORY_ROOT` | fix_request 状态 / 域记忆根 |
| `CHIP_AGENT_AUTO_DISTILL` | 自动蒸馏开关(默认 1) |
| `CHIP_AGENT_AUDIT_EVERY` / `_AUTO_CLEAN` | 巡检间隔(默认 20)/ 自动清洗(默认 0) |
| `CHIP_AGENT_PLANNER` / `_LLM_*` | keyword / llm / conversational(+OPENAI_API_KEY) |
| `UVM_HOME` / `UVM_VERSION` / `VERDI_HOME` | 库解析 / 版本选择 / NPI 激活门 |

## 5. 使用方式

### 5.1 Claude/Codex 会话
直接自然语言("生成 testbench"、"反例分析 根因定位"、"做一次覆盖分析"、
"加载波形并查看占空比") — planner 路由到对应 recipe,工具自动出现。

### 5.2 CLI
```bash
python3 -m chip_ai_agent.cli "生成 testbench" --db runs.db --history
```

### 5.3 工程师实操流程
分析 RTL → 写 test plan → `chip_generate_testbench` →
`chip_check_uvm_compliance`(门禁)→ 编译仿真(VCS 缺席时降级给 ready_command,
或经 verif-agent-mcp)→ FSDB 取证(NPI 层)→ 诊断 → 修复 → 复验 —
每轮 run 自动落库并进入学习闭环。

## 6. 部署生命周期

```bash
# 全新部署(清理+备份+重装, 见 .deploy_backup_<ts>/)
# 回滚: 把 .deploy_backup_<ts>/ 内文件移回原路径
# 巡检: chip_infra_detect 盘点全部工具/库/语料/部署状态
# 健康: claude mcp list / curl http://127.0.0.1:8001/health (verif-agent)
```

## 7. 故障排查

| 症状 | 处理 |
|---|---|
| `⏸ Pending approval` | claude 应用内批准一次(项目信任,永久) |
| 工具报 "no MCP server configured" | 外部技能需配置 server(registry 技能无 server 时进 plan.missing) |
| NPI 工具降级 | 需真实 Verdi(`module load synopsys`),不伪造激活门 |
| SDK 未生效 | `bash chip_ai_agent/install_sdk.sh` 或离线 wheelhouse 安装 |
| 语料 0 命中 | 索引需重建(dvcon: build;ug: 手册放入索引根后 build) |

## 8. 环境变量全表 (2026-10-19 审计核对)

| 变量 | 作用 |
|---|---|
| CHIP_AGENT_TEMPLATE_TB | UVM 模板工程根 |
| CHIP_AGENT_MODULEFILES | modulefile 搜索路径 (':'分隔) |
| CHIP_AGENT_EDA_ROOTS | EDA 工具搜索根 (':'分隔) |
| CHIP_AGENT_NPI_ROOT | NPI kit 根 (python/lib/inc) |
| CHIP_AGENT_UVM_ROOT | Accellera UVM 参考库 |
| CHIP_AGENT_UVM_TGZ_ROOT | UVM tarball 父目录 |
| CHIP_AGENT_UG_ROOT | UG 手册语料根 |
| CHIP_AGENT_DVCON_ROOT | DVCon 语料根 (默认随包 dvcon/) |
| CHIP_AGENT_UVM_SRC_ROOT | UVM 源码知识库 (默认随包 uvm_src_kb/) |
| CHIP_AGENT_MANUAL_SCAN_ROOT | 手册扫描根 (默认: 部署包父目录) |
| CHIP_AGENT_TECH_MANUAL_ROOT | 手册语料输出根 (默认: 随包 corpus/technical_manuals) |
| CHIP_AGENT_EXAMPLE_UART | Verification Academy UART 示例树 |
| CHIP_AGENT_VERIF_AGENT_BIN/_CONFIG | verif-agent-mcp 可执行/配置 |
| CHIP_AGENT_WHEELHOUSE / _PYTHON | 离线安装: wheelhouse 与 venv python |
| CHIP_AGENT_HOME | install_integration.sh 的 agent 根 |
