# DVCon 2025–2026 AI 验证趋势分析与本 Agent 的迭代映射

> 数据来源说明: 本次联网检索 API 配额耗尽(429), 无法实时抓取 DVCon 官网论文列表。
> 以下 2025 年内容基于公开已知的 DVCon US 2025 议题方向归纳; 2026 年条目为
> ⚠️ **推断性趋势**(基于 2025 方向的延续与工业界公开演讲线索), 待联网恢复后复核。

## 1. DVCon 2025 公开主题归纳

| 主题 | 核心做法 | 对本 Agent 的映射 |
|---|---|---|
| LLM 生成 UVM 组件 | 用 LLM 从 spec 生成 driver/monitor/sequence, 强调"生成→编译→仿真"闭环校验, 不接受裸生成 | 已有 executor 循环(每步落库); 后续可加 lint/sim gate |
| Spec-to-SVA 自动生成 | 从 spec/RTL 推断协议断言, 以**断言命中率/误报率**为反馈迭代 | 新增配方 `spec_to_sva`: 源码+接口识别 → evaluate_assertion → 断言统计回喂 |
| Agentic Debug Copilot | 多轮 agent 循环, 波形/日志/源码交叉取证 | 本 Agent 主体; 新增 `ConversationalPlanner` 多轮回喂 |
| 覆盖率驱动智能激励 | 用覆盖洞定位欠激励场景, AI 生成针对性 stimulus | 新增配方 `coverage_driven_stimulus`: 覆盖洞→表达式→源码回溯→信号验证 |
| RAL/寄存器测试自动化 | 寄存器模型驱动的验证计划条目生成 | 可扩 recipe(暂列 backlog) |
| 形式化 + AI (功能安全) | SVA 辅助生成用于 ISO 26262 场景, 要求可审计 | SQLite RunReport 持久化已满足可审计基线 |

## 2. ⚠️ 2026 推断趋势

1. **Agentic loop 以编译/仿真/覆盖率为 reward**: planner 不再单轮, 而是把
   "上次运行结果"作为下一轮规划输入 → 已实现 `ConversationalPlanner.observe()`
   + `LLMPlanner.refine()`(plan-critique-retry)。
2. **vplan 条目 → 测试 → 覆盖回链**: 验证计划条目自动追踪到覆盖率数据;
   本 Agent 的 `runs`/`steps` SQLite 表是回链的数据底座。
3. **LLM 阅读波形/日志做因果诊断**: 从"找 force 语句"升级到"为什么这条总线
   在该时刻挂死"; `driver_trace`/`x_prop_debug` 配方已按此组织取证链。
4. **安全场景要求可审计确定性 AI**: 每一步技能调用必须可复现、可回放 →
   `report_store` 已记录全部步骤; 可加 hash 链(后续迭代)。

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
