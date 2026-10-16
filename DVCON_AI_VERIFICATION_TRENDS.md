# DVCon 2025–2026 AI 验证趋势分析与本 Agent 的迭代映射

> 数据来源说明: 2026-10 **联网复核完成** — 2025/2026 论文语料已按
> 段落/方法描述/结论切分并转化为模型可识别调用的 recipe/skill,
> 见 **`DVCON_2025_2026_CORPUS.md`**(本文件的实证校正版, 含出处链接与
> 调用映射表)。第 2 节由推断趋势更新为实证结论。

## 1. DVCon 2025 公开主题归纳

| 主题 | 核心做法 | 对本 Agent 的映射 |
|---|---|---|
| LLM 生成 UVM 组件 | 用 LLM 从 spec 生成 driver/monitor/sequence, 强调"生成→编译→仿真"闭环校验, 不接受裸生成 | 已有 executor 循环(每步落库); 后续可加 lint/sim gate |
| Spec-to-SVA 自动生成 | 从 spec/RTL 推断协议断言, 以**断言命中率/误报率**为反馈迭代 | 新增配方 `spec_to_sva`: 源码+接口识别 → evaluate_assertion → 断言统计回喂 |
| Agentic Debug Copilot | 多轮 agent 循环, 波形/日志/源码交叉取证 | 本 Agent 主体; 新增 `ConversationalPlanner` 多轮回喂 |
| 覆盖率驱动智能激励 | 用覆盖洞定位欠激励场景, AI 生成针对性 stimulus | 新增配方 `coverage_driven_stimulus`: 覆盖洞→表达式→源码回溯→信号验证 |
| RAL/寄存器测试自动化 | 寄存器模型驱动的验证计划条目生成 | 可扩 recipe(暂列 backlog) |
| 形式化 + AI (功能安全) | SVA 辅助生成用于 ISO 26262 场景, 要求可审计 | SQLite RunReport 持久化已满足可审计基线 |

## 2. 2026 实证结论 (联网复核, 详见 DVCON_2025_2026_CORPUS.md)

1. **因果图驱动的根因分析成为共识** (FVDebug, DVCon US 2026 最佳论文第 3):
   显式因果边使 Quality@Best 0.474→0.956, Pass@1 71.1% →
   已落地 `fv_failure_debug` recipe + `formal_failure_debug` SKILL.md。
2. **Agentic 反思循环 > 模型能力** (Saarthi 2025 实证: GPT-3.5+agentic 超
   GPT-4 零样本; 首代自主成功率 ~40-50%) →
   `agentic_formal_flow` recipe; 本 Agent 的 ConversationalPlanner/observe
   即同构闭环。
3. **双记忆 RAG 按项目成熟度动态加权** (Samsung Spec-RAG: 34 周/398 缺陷
   27% 调试时间缩减, Type-1 错误最高 75%) →
   `spec_rag_verification` recipe; 本 Agent 域记忆+运行库即 STM/LTM 底座。
4. **失败签名聚类缩减回归 TAT 12-43%** (DVCon EU 2025 #127) →
   `regression_triage` recipe; skill_failure_strategies 矩阵已实现签名底座。
5. **2026 词汇表**: Spec-RAG / Knowledge Graph / Multi-Agent / MCP /
   Agentic Sign-off / Autonomous Regression —— 全自动签核仍不可行,
   人工门禁 + 可审计是共同底线 (与本 Agent 的 fix_request 状态机一致)。

## 3. 本轮已落地的代码迭代

- `recipes.py`: 新增 `spec_to_sva`、`coverage_driven_stimulus`、`rtl_code_review` 三条配方。
- `planner.py`: `LLMPlanner.refine()` 自审重试; `ConversationalPlanner` 把上次
  RunReport 摘要回喂 LLM, 支持多轮增量追问; `Planner` Protocol 增加 `refine`。
- `agent.py`: `RunReport.summary()` + run 结束自动 `observe()` 回喂 planner。

## 4. 待联网恢复后的验证清单

  1. 复核 DVCon US 2026 / DVCon Europe 2026 议题页, 校正第 2 节推断。
  2. 抽取 2025 高相关论文摘要, 对照 `spec_to_sva` 配方的技能链是否需要补
     evaluate_assertion 之外的反馈技能。
  3. 检查 RAL 自动化是否有可复用的 MCP 技能(当前 registry 未扫描到)。
