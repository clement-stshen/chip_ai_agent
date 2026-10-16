# chip_ai_agent 功能说明书

> 版本 2.0.0 · 2026-10 · 配套文档: [INSTALL_CONFIG.md](INSTALL_CONFIG.md)

## 1. 系统定位

面向芯片研发与验证的本地智能 Agent:意图 → 规划 → 技能/MCP 工具链执行 →
报告落库 → 主动记忆与学习闭环。双模式 MCP 服务(SDK v2 主路径 + 零依赖
legacy 回退),支持 Claude Code / Codex / 任意 MCP 客户端。

## 2. 总体架构

```
客户端(Claude/Codex/CLI) ── MCP stdio / streamable-HTTP ──┐
                              mcp_server.py (双模式入口)   │
   SDK 模式: sdk_server (MCPServer v2, 代码生成+工具缓存)   │
   legacy:  mcp_tools (零依赖 JSON-RPC)                    │
                              tool_registry (TOOL_DEFS 唯一事实源)
                                        │
      ChipAgent (plan/run + 学习闭环) ──┬─ local_tools (32 本地工具)
                                        ├─ npi_tools (pynpi 波形层, 21 工具)
                                        ├─ eda_tools (VCS/Verdi/NPI/UVM 发现)
                                        └─ mcp_adapter (外部 server 客户端)
      记忆: experience(JSONL+TF-IDF) / report_store(SQLite) / digital_memory
      语料: dvcon_index / ug_index / npi_index / examples_index
      配置: site_paths (全部 env 可覆盖)
```

## 3. MCP 工具面(24 个)

### 3.1 规划与执行
| 工具 | 功能 |
|---|---|
| `chip_agent_plan` | 意图 → recipe/步骤/缺失技能/记忆注入(成功回放、风险、run_history、recipe_regression、有效变体) |
| `chip_agent_run` | 全流程执行 + 逐步进度 + 报告落库 + 失败反思(相似历史+技能级策略)+ 自动蒸馏 |
| `chip_agent_recall` | 做事前记忆召回:相关经验(新近度/环境加权)、域知识、有效变体、技能风险与修复策略 |

### 3.2 验证环境
| 工具 | 功能 |
|---|---|
| `chip_generate_testbench` | UVM 1800.2-2020.3.1 模板生成(12 文件) |
| `chip_check_uvm_compliance` | IEEE 1800.2-2020 13 类静态合规门禁 |
| `chip_run_simulation` | VCS 编译+仿真+UVM 报告解析(无 VCS 优雅降级+ready_command) |
| `chip_open_waveform` | Verdi 打开 FSDB(降级给 ready 命令) |
| `chip_analyze_eda_log` | VCS/UVM/Verdi/LSF 日志迭代分析(分类+策略+下一步) |

### 3.3 记忆与学习
| 工具 | 功能 |
|---|---|
| `chip_agent_history` / `chip_agent_stats` | 运行轨迹 / 技能成功率(样本量下限) |
| `chip_memory_search` / `chip_memory_distill` | 域经验 TF-IDF 检索/写入 / knowledge.md 蒸馏 |
| `chip_qor_trends` | 跨 run QoR 趋势与回归检测 |
| `chip_design_state` | 验证↔RTL fix_request 状态机(迭代上限/divergence/升级) |
| `chip_design_pipeline` | spec→tape-out 流水线(plan/status/run/next/re_verify) |

### 3.4 知识语料
| 工具 | 功能 |
|---|---|
| `chip_ug_search` | VCS+Verdi+UVM 手册检索(章节/操作步骤切分, product/kind 过滤) |
| `chip_dvcon_search` | DVCon 2025/2026 论文语料(段落/方法/结论切分, year/kind/tag 过滤) |
| `chip_npi` | NPI C API 检索(24 头文件/506 API) |
| `chip_examples` | 黄金 UVM TB 范例库检索 |
| `chip_domain_flows` / `chip_flow_guide` | 15 域机器可读流程 / 四相研发流程 |
| `chip_infra_detect` | 24 开源 + 7 商用工具 detect-only + wrapper/MCP 部署状态 |
| `chip_edatools` | VCS/Verdi/NPI/UVM 库/verif-agent 统一盘点 |

## 4. 规划与配方(48 recipes)

- **调试取证**: waveform_forensics / driver_trace / x_prop_debug / timing_sequence /
  source_navigation / onesearch / trace_workflows / design_inventory 等
- **验证流**: uvm_verification_flow(8 阶段)/ testbench_generation / simulation_run /
  log_analysis / verif_agent_flow(仿真→诊断→覆盖闭环)
- **DVCon 论文转化**: fv_failure_debug(FVDebug 四段流水线)/ agentic_formal_flow(Saarthi)/
  spec_rag_verification(Samsung 双记忆)/ coverage_from_requirements / regression_triage /
  uvm_env_factory(TBGen)
- **跨域**: 16 域 digital-agents 流 + fix_request_pipeline + full_flow_rtl2gds
- 触发词双语、防截胡(宽词避让)、0 phantom 技能保证(注册表∪本地工具全覆盖)

## 5. 主动记忆与学习(五层闭环)

| 层 | 能力 |
|---|---|
| 采集 | 结构化 step 轨迹(failure_class/retry_strategy/duration)、环境指纹、试错 attempt |
| 触发 | 失败即反思、自动蒸馏(≥5 条域失败)、QoR 回归守卫、周期巡检(每 N 次 run) |
| 检索 | TF-IDF + 时间衰减(30 天半衰期)+ 环境降权、三层合并(知识/经验/轨迹)、成功回放 |
| 闭环 | 成功率标注+风险列表、有效步骤变体沉淀与回放(recipe 自进化,带溯源)、LLM refine 可选接线 |
| 遗忘 | 重试去重(repeat_count)、自动清洗(env 门控)、审计可追溯 |

## 6. NPI 波形执行层(21 工具)

pynpi-backed 本地实现(真实 Verdi 激活,否则统一降级契约):
会话族(load/get_active/set_active_fsdb,常驻 worker)/ 查询族(value_at/首末值/
跳变/第N次/时长/翻转统计/X 未知/序列 SigValueEval/最大延迟)/ 层次近似 /
纯文件工具(read_specific_lines/search_in_source_code_result)。
激活门与库自身一致(`$VERDI_HOME/bin/npi` 可读),无伪造无绕过。

## 7. 资源与提示词(SDK 模式)

- Resources: chip://skills、chip://skills/{domain}、chip://runs、chip://design/state、
  chip://flows/{domain}、chip://guide
- Prompts: chip-plan、chip-debug
- streamable-HTTP: `CHIP_AGENT_TRANSPORT=streamable-http`(团队共享,启动预热+巡检)

## 8. 错误契约与可观测性

- 统一 ToolError 封套: {error, error_code, retryable}(unknown_tool/timeout/invalid_params/internal)
- 全路径 metrics(每工具调用耗时/错误、SDK 缓存命中,snapshot 可查)
- 进度: chip_agent_run 逐步 + 6 个长操作粗粒度(协议兼容 2024-11-05,无 message 字段)
- 并发安全: sqlite WAL+锁、agent 操作锁、单读者管道测试基建

## 9. 性能基线

| 指标 | 值 |
|---|---|
| 启动+initialize (SDK) | ~0.5s/会话(导入栈,每会话一次) |
| tools/list | 2ms |
| plan 冷/热 | 40ms / 4ms(160 技能注册表单例缓存) |
| SDK 工具缓存 | sdk_server 内 TTL 缓存(metrics 计数) |
| 语料检索 | 哈希 TF-IDF 稀疏向量,毫秒级(UG 129 本/35,042 单元) |

## 10. 测试保障

218 项回归(协议双模式、学习闭环、语料精准性、NPI 降级、UVM 解析、
安全加固 shell-free、路径配置、并发)。
