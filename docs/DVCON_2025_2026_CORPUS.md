# DVCon 2025 / 2026 论文语料(联网复核版)

> 数据来源: 2026-10 联网检索复核(2025 版为配额耗尽推断, 本文档为其校正)。
> 切分单元: **段落**(摘要/引言原文要点) / **方法描述**(可执行方法链) /
> **结论**(实验数字与启示)。每条附 **模型识别调用映射**: 触发词 → recipe
> (recipes.py) / skill, 使 planner 按意图路由、模型按语料识别调用。

---

## 1. FVDebug: LLM 驱动的形式化失败根因分析(最佳论文第 3 名)

- **出处**: NVIDIA (Yunsheng Bai, Ghaith Bany Hamad, Chia-Tung Ho, Syed Suhaib,
  Haoxing Ren), DVCon US 2026 Best Paper Presentation 3rd;arXiv 2510.15906;
  [dvcon-proceedings](https://dvcon-proceedings.org/document/fvdebug-an-llm-driven-debugging-asst-for-automated-root-cause-analysis-of-formal-verif-failures/)
- **段落**: 调试 FV 失败是硬件流程中耗时最长的瓶颈之一——工程师人工追溯多周期
  反例、分析波形并对照规格,每个 bug 数小时至数天。FVDebug 整合波形、RTL 与
  规格,把失败轨迹转化为可行动洞察("transform failure traces into
  actionable insights")。
- **方法描述** (四段流水线):
  1. **因果图合成**: 平铺 CEX 轨迹 → 信号事件 DAG(节点 = signal@cycle=value,
     边 = 直接因果依赖;JasperGold `visualize -why` 递归依赖追踪, 默认 20 周期);
  2. **图扫描器**: 批量 LLM 节点分析, for-and-against 正反论证提示(消确认偏误),
     token 感知分批;
  3. **Insight Rover**: agentic 假设管理/探索(树状思维/多智能体辩论),
     生成、细化并排序竞争假设;
  4. **Fix Generator**: 生成具体 RTL patch 与调试报告(排序假设 + 因果时间线 +
     diff 级建议)。
- **结论**: SVA-Eval-Human(38 真实失败): Quality@Best 0.956 / NDCG@5 0.983 /
  MRR 0.858 / Kendall's τ 0.708 / **71.1% Pass@1 / 86.8% Pass@5**;Direct LLM
  仅 0.783/0.605,Flat Trace 仅 0.474 —— **显式因果关系是准确根因识别的基础**;
  移除 Insight Rover 质量骤降(0.795);两个生产级 CEX(50 万+ 行代码, 因果链
  15 层) 4-6 分钟内给出 Expert/Strong Match 诊断。
- **调用映射**: "反例分析 / counterexample / 根因定位 / fv debug" →
  `fv_failure_debug` recipe: evaluate_assertion → explain_design_from_source →
  agentic_debug_workflow → sva_assertion_generation(对应因果图→扫描→rover→fix)。

## 2. Saarthi: 第一个 AI 形式化验证工程师(最佳口头发表第 2 名)

- **出处**: Infineon (Aman Kumar, Deepak Narayan Gadde, Keerthan Kopparam
  Radhakrishna, Djones Lettnin), DVCon US 2025 2nd place;arXiv 2502.16662;
  [dvcon-proceedings PDF](https://dvcon-proceedings.org/wp-content/uploads/1048.pdf)
- **段落**: 首个全自主 AI 形式化验证工程师: 用 agentic LLM 工作流
  (CrewAI/AutoGen/LangGraph) 端到端验证 RTL——规划、工具调用、多智能体协作。
- **方法描述**: coder/critic 反思循环(生成 → 自审 → 修订);LLM 生成 SVA 并驱动
  形式化工具;反馈(证明/反例/编译错误)作为下一轮输入;**agentic/少样本工作流
  显著优于零样本**(GPT-3.5 + agentic 循环超过 GPT-4 零样本)。
- **结论**: 自主成功率 ~40-50%(第一代);FIFO SVA 任务 100% 通过;启示: 闭环
  反思 > 模型能力本身——与 DVCON 2026 对全自动签核的审慎态度一致。
- **调用映射**: "agentic formal / saarthi / coder critic / 形式化多智能体" →
  `agentic_formal_flow` recipe: sva_assertion_generation → assertion_feedback_refine
  → evaluate_assertion → formal-verification。

## 3. Unified AI-Driven Verification: Spec-RAG + 记忆网络

- **出处**: Samsung (Seonghee Yim, Insoo Jang, Hanna Jang, Youngsik Kim),
  DVCon US 2026;
  [dvcon-proceedings PDF](https://dvcon-proceedings.org/wp-content/uploads/67-Unified-AI-Driven-Verification-Combining-Spec-RAG-Memory-Networks-and-Generative-AI.pdf)
- **段落**: 把验证知识检索统一为双记忆 RAG: 短期记忆(日志/MongoDB/实时 sanity
  数据)与长期记忆(规格 Oracle RDB + HippoRAG 知识图谱 + 跨版本修订历史)。
- **方法描述**: 按项目成熟度相位对 STM/LTM 动态加权;LLM 驱动决策逻辑与图推理
  (graph reasoning) 做 issue 分类(如 Type-1 = 信息不匹配/误报)。
- **结论**: 真实 SoC 项目 34 周 / 398 个 Jira 缺陷: 动态加权 **27% 调试时间缩减**
  (静态双记忆 11%, 基线 0%);Type-1 信息不匹配类错误效率提升最高 **75%**。
- **调用映射**: "spec rag / hipporag / 知识图谱验证 / 双记忆" →
  `spec_rag_verification` recipe: search_domain_memory(LTM) → flow_guide(决策)
  → analyze_eda_log(STM 现场)。本 Agent 的域记忆 + 运行库即 STM/LTM 底座。

## 4. LLM 功能覆盖生成与自动评估框架

- **出处**: Labuda, Zachariášová, Matěj (MUNI), DVCon Europe 2025。
- **段落**: 用 LLM 从自然语言验证需求自动生成功能覆盖代码(UVM 语境),
  并给出受控自动评估框架。
- **方法描述**: NL 需求 → covergroup/coverpoint 代码生成 → 语料对照自动评估
  (可控数据集, 指标化对比)。
- **结论**: 有前景但局限——生成质量依赖需求粒度与模板;评估框架本身是复用资产。
- **调用映射**: "nl2cov / covgen / coverpoint 生成" →
  `coverage_from_requirements` recipe: vplan_coverage_traceability(回链评估) →
  coverage_driven_stimulus(覆盖洞关闭)。

## 5. The Test Bench Factory (TBGen)

- **出处**: Infineon, DVCon Europe 2025。
- **段落**: 通用 UVM-SV testbench 生成器, 面向 VIP/TB 复用。
- **方法描述**: 元数据驱动(非 LLM)的 VIP 分类体系 iVC/mVC/sysVC;
  模板+生成器流水线;与生成环境工厂化。
- **结论**: 生成器路线在确定性/复用上仍优于纯 LLM 生成——2025 年 UVM 环境
  生成的主流仍是元数据驱动。
- **调用映射**: "tbgen / 验证环境工厂 / vip 复用 / ivc mvc" →
  `uvm_env_factory` recipe: generate_testbench → check_uvm_compliance
  (模板元数据即 iVC 分类的本地对应物)。

## 6. ML-Based Regression Failures Triage and Debug

- **出处**: DVCon Europe 2025 paper 127。
- **段落**: 自动失败聚类——识别重复/相似失败, 签名复制, 日志/波形定位缩小
  调试范围。
- **方法描述**: 失败签名提取 → 聚类/归并 → 相似案例检索 → 调试范围收敛;
  辅以回归压缩与负载均衡。
- **结论**: **12-43% 回归 TAT 缩减**。
- **调用映射**: "失败聚类 / failure triage / 失败签名" →
  `regression_triage` recipe: analyze_eda_log(签名) → search_domain_memory
  (相似解法) → design_state_pipeline(重复失败走 fix_request 闭环)。
  本 Agent 的 skill_failure_strategies 矩阵已实现签名聚类底座。

## 7. Debug Assist: LLM 引导的 FPV 失败调试

- **出处**: Kevin Bhensdadiya et al., DVCon India 2026 Session 2C(同场:
  Post-Simulation Firmware Debug from Waveforms/PC Traces)。
- **段落/方法**: LLM 引导的 FPV 失败调试框架;波形+PC 轨迹+源码联合取证。
- **结论/启示**: 与 FVDebug 同一方向——波形/源码多源取证是根因分析共识。
- **调用映射**: 并入 `fv_failure_debug` recipe(同一技能链)。

## 8. 会议级结论(DVCon US 2026 面板与主题)

- 面板 "Is AI the Key to Ending the Verification Bottleneck?"(Vishal Karna,
  Qualcomm);Keynote "From Pixels to Tokens"(Stuart Oberman, NVIDIA):
  agentic workflow 成为设计/验证规模化必需品。
- 2026 词汇表: Spec-RAG / Knowledge Graph / GraphRAG / Memory / Multi-Agent /
  **MCP** / Agentic Sign-off / Autonomous Regression —— 与 2025 单点工具
  (VIP 实例化、回归 triage、Saarthi)形成代际差异。
- 审慎共识: 全自动签核尚不可行(Saarthi 首代 ~40%), LLM testbench 论文仍
  限于小型有界设计;可审计、闭环、人工门禁是共同底线 —— 与本 Agent 的
  fix_request 状态机 + checkpoint 人工审批 + RunReport 全量落库一致。

## 附: 语料→代码转化清单(本轮已落地)

| 论文 | 新 recipe | 新 skill |
|---|---|---|
| FVDebug | `fv_failure_debug` | `formal_failure_debug`(SKILL.md 方法论) |
| Saarthi | `agentic_formal_flow` | — |
| Samsung Spec-RAG | `spec_rag_verification` | — |
| LLM coverage (MUNI) | `coverage_from_requirements` | — |
| DVCon EU #127 | `regression_triage` | — |
| TBGen | `uvm_env_factory` | — |
| 趋势复核 | DVCON_AI_VERIFICATION_TRENDS.md 第 2 节由推断改为实证 | — |
