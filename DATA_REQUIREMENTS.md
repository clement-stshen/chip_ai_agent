# 提升 AI Agent 所需资料清单与脏数据清洗指南

本文回答两个问题:
1. **要提供哪些资料才能提升 Agent?** (按 Agent 组件映射)
2. **脏数据如何清洗?** (数据质量工具 + 流水线)

---

## 一、资料清单 (按提升目标映射)

### A. 提升 Planner (规划质量)

| 资料 | 格式 | 用途 | 优先级 |
|---|---|---|---|
| 历史 debug 意图 → 成功 recipe 的配对记录 | JSONL (`intent, recipe, steps, outcome`) | 微调 trigger 词 / LLM few-shot | ★★★ |
| 典型调试工单 (JIRA/ticket 文本) | 纯文本 | 扩充 `match_intent` 触发词与 LLMPlanner 提示 | ★★★ |
| DVCon/论文方法论 (如本次 2025 分析) | Markdown | 沉淀为新 recipe / SKILL.md | ★★ |
| 真实 MCP server 的 tools/list 输出 | JSON | 校正 recipes 里的技能名(当前 92 加密技能无法验证) | ★★★ |

### B. 提升 Skills (技能库)

| 资料 | 格式 | 用途 |
|---|---|---|
| **解密后的 SKILL.md**(当前 90/92 加密) | 标准 skill 目录 | `parse_skill_md` 提取 Method/Steps/Pitfalls, 反哺 recipes |
| 内部 RTL coding guideline | PDF/MD | 生成 `rtl_code_review` 类新技能 |
| 断言库 (SVA) | .sva | 扩充 `sva_assertion_generation` 的模式库 |
| 覆盖率报告样例 (VCS -cm / ucdb 导出文本) | 文本/CSV | 校准 `coverage_driven_stimulus` 的阈值与分类 |
| 寄存器手册 (UART 16550 类) | PDF/表格 | RAL 自动化 recipe 的 golden 参考 |

### C. 提升 Experience (经验回喂)

| 资料 | 格式 | 用途 |
|---|---|---|
| 真实失败案例: 意图 + 失败技能 + 根因 + 修复动作 | JSONL (见下方 schema) | 经验库种子数据, plan() 自动检索注入 |
| 波形取证结论 (信号/时刻/根因行) | 结构化文本 | `waveform_causal_diagnosis` 的训练样例 |
| 覆盖洞 → 定向测试的闭环记录 | 表格 | `vplan_coverage_traceability` 证据链 |

**经验记录 schema** (与 `experience.py` 对齐):
```json
{"intent": "...", "recipe": "...", "status": "partial",
 "failed_skills": ["..."], "failure_class": "functional",
 "retry_strategy": "refine", "reason": "根因一句话",
 "fix": "实际修复动作", "run_id": 123, "step_count": 4}
```

### D. 提升 Testbench 生成 (UVM 模板)

| 资料 | 格式 | 用途 |
|---|---|---|
| 更多 DUT 类型参考 (APB/SPI/I2C/AXI) | RTL + spec | 扩充模板库, `generate_testbench` 支持选型 |
| 内部 UVM env 编码规范 | MD | 校准 `check_uvm_compliance` R1-R13 |
| 历史合规检查误报样本 | 违规输出 | 持续修复检查器 (如本次 UART 工程暴露 4 缺陷) |

### E. 提升 LLM Planner

| 资料 | 格式 | 用途 |
|---|---|---|
| 200+ 条 intent→plan 标注对 | JSONL | few-shot 注入 / 微调本地模型 |
| 规划失败案例 (错配 recipe) | 文本 | 构建 `refine()` 的 critique 语料 |

---

## 二、脏数据分类与清洗

### 已识别的脏数据类型

| 类型 | 表现 | 危害 | 处置 |
|---|---|---|---|
| **无信息记录** | `status=empty` / `step_count=0` (无 MCP server 跑出的空 run) | 污染经验检索与 stats | 删除 |
| **环境噪音** | 全步骤 ERR 且 reason 以 "LLM planner unavailable" 开头 | 误当失败知识回喂 | 删除 (可 `--keep-degraded` 保留) |
| **重复记录** | (intent, recipe, failure_class, failed_skills) 完全相同 | 检索排名偏置 | 去重保最新 |
| **畸形行** | 非法 JSON / 缺必填字段 | 加载报错 | 删除 |
| **空 run** | SQLite runs 表有记录但 steps 为 0 | stats 失真 | 删除 |
| **孤儿 steps** | steps.run_id 无对应 run | 外键断裂 | 删除 |
| **陈旧生成目录** | /tmp/uvm_tb_gen_* 超 24h | 磁盘占用 | `--prune-stale-dirs` |
| **加密技能误计** | SKILL.md 为 Fernet blob | registry 显示可用但无法执行 | 审计标记 (不删) |

### 清洗工具 (backup-first, 永不直接销毁)

```bash
# 审计 (只读, 发现问题 exit 1)
python3 chip_ai_agent/data_quality.py --experience memory/experiences.jsonl --db runs.db

# 清洗 (自动备份 .bak.<timestamp>)
python3 chip_ai_agent/data_quality.py --experience memory/experiences.jsonl --db runs.db --clean

# 顺带清理 >24h 的生成目录
python3 chip_ai_agent/data_quality.py --clean --prune-stale-dirs

# 保留 LLM 降级记录 (如需分析网络故障模式)
python3 chip_ai_agent/data_quality.py --experience exp.jsonl --clean --keep-degraded
```

### 清洗流水线 (建议周期: 每周或每次大量测试后)

```
原始数据 → audit (只读体检)
        → clean (备份 + 去脏)
        → 复审 audit (issues 全 0)
        → 注入 Agent (experience 检索 / stats 展示)
```

### 质量红线 (写入 experience 前应满足)

1. `status != empty` 且 `step_count > 0`
2. 必填字段齐全 (intent/recipe/status/failure_class)
3. 失败记录必须带具体 failed_skills 与根因 reason
4. 同一 (intent, recipe, failure) 只保留最新一条
5. 环境性失败(license/网络/MCP 未配置)不入库, 或打标隔离

---

## 三、提升路线图 (资料到位后的动作)

1. **解密技能包** → `parse_skill_md` 批量解析 → 自动校正 recipes 技能名
2. **导入 200+ 标注对** → LLMPlanner few-shot + KeywordPlanner trigger 扩充
3. **导入真实失败案例** → 经验库种子 → plan() 自动注入历史修复
4. **扩充 DUT 模板** (APB/SPI/I2C) → `generate_testbench` 参数化选型
5. **持续合规检查器进化** → 每个新真实工程跑一遍, 误报即修 (UART 已修 4 项)
