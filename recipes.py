"""Workflow recipes: intent -> ordered skill/tool plans for chip debug & verification."""

import re

RECIPES: dict[str, dict] = {
    "x_prop_debug": {
        "title": "X 值 / 未初始化问题定位",
        # never a bare "x": substring matching sent any intent containing
        # the letter x (e.g. "mux issue") into this X-propagation flow
        # bare "x" is now safe: short ASCII triggers match on word
        # boundaries only (see _trigger_hit)
        "trigger": ["x", "x value", "x propagation", "xprop", "x source",
                    "signal x", "unknown value", "uninitialized",
                    "未初始化", "x 值", "x值", "x 传播", "x源"],
        "steps": [
            {"skill": "waveform_causal_diagnosis", "why": "方法论: 从现象时刻沿驱动链回溯根因, 而非只报现象"},
            {"skill": "trace_x_workflow", "why": "沿驱动链回溯 X 源头"},
            {"skill": "trace_backward_workflow", "why": "必要时继续向源端追溯"},
            {"skill": "get_signal_value_at_time", "why": "确认问题时刻各层信号值"},
            {"skill": "detect_unknown_and_get_previous_or_next_transitions", "why": "找 X 首次出现与前后跳变"},
            {"skill": "get_source_code", "why": "定位到 RTL 赋值代码"},
            {"skill": "agentic_debug_workflow", "why": "方法论: 失败步骤禁止原样重试, 3 轮强制收敛"},
        ],
    },
    "driver_trace": {
        "title": "信号驱动链追溯",
        "trigger": ["driver", "who drives", "驱动链", "active driver", "active memory"],
        "steps": [
            {"skill": "trace_signal", "why": "启动交互式信号追踪"},
            {"skill": "trace_chain_driver_workflow", "why": "多级驱动链展开"},
            {"skill": "trace_clock_driver_workflow", "why": "时钟树来源确认"},
            {"skill": "trace_active_driver_workflow", "why": "活动驱动者动态追溯"},
            {"skill": "trace_active_memory_workflow", "why": "存储器活动状态追溯"},
            {"skill": "static_connectivity_trace", "why": "静态连通性交叉验证"},
            {"skill": "jump_to_source", "why": "跳转 RTL 源码"},
        ],
    },
    "assertion_failure_triage": {
        "title": "断言失败分诊",
        "trigger": ["assert", "sva", "断言失败", "断言"],
        "steps": [
            {"skill": "get_assertion_statistics", "why": "整体通过/失败分布"},
            {"skill": "get_assertion_status_by_name", "why": "按名查单条断言状态"},
            {"skill": "analyze_assertion", "why": "单条断言行为分析"},
            {"skill": "evaluate_multiple_assertions", "why": "批量评估相关断言"},
            {"skill": "check_handshake_stability", "why": "握手协议类断言专项检查"},
            {"skill": "get_signal_value_at_time", "why": "失败时刻现场取证"},
            {"skill": "add_and_save_assertion", "why": "补写回归防护断言"},
            {"skill": "assertion_feedback_refine", "why": "方法论: 用断言统计驱动 SVA 修订与用例补齐 (零命中=无效断言)"},
        ],
    },
    "coverage_closure": {
        "title": "覆盖率收敛",
        "trigger": ["coverage", "覆盖"],
        "steps": [
            {"skill": "highlight_uncovered_items_in_source_view", "why": "源码视角定位未覆盖项"},
            {"skill": "add_exclusions_for_uncovered_items", "why": "合法不可达项豁免"},
            {"skill": "apply_tool_on_signals_under_scope", "why": "对 scope 内批量补充分析"},
            {"skill": "coverage_driven_stimulus", "why": "方法论: 覆盖洞回溯 RTL 条件, 不可达项不消耗迭代预算"},
            {"skill": "vplan_coverage_traceability", "why": "方法论: vplan 条目↔测试↔覆盖双向回链"},
        ],
    },
    "power_analysis": {
        "title": "功耗分析与 UPF 电源域核对",
        "trigger": ["power", "upf", "功耗", "电源域"],
        "steps": [
            {"skill": "power_agent", "why": "UPF 综合查询入口 (电源域/供应集/隔离/保留/PST)"},
            {"skill": "get_power_objects", "why": "枚举电源对象"},
            {"skill": "get_power_information_for_instance", "why": "实例级功耗信息"},
            {"skill": "get_power_information_for_signal", "why": "信号级功耗信息"},
            {"skill": "analyze_power_object_status_at_time", "why": "时间点电源状态核对"},
            {"skill": "get_power_object_relationship", "why": "电源域/隔离/保留关系"},
            {"skill": "show_power_object_definition", "why": "电源对象定义定位"},
        ],
    },
    "design_onboarding": {
        "title": "新设计快速上手",
        "trigger": ["explain", "architecture", "架构", "新设计", "入门"],
        "steps": [
            {"skill": "import_design", "why": "加载设计/FSDB"},
            {"skill": "find_top_modules", "why": "顶层识别"},
            {"skill": "show_hierarchy_tree", "why": "层级结构总览"},
            {"skill": "identify_micro_architecture_types", "why": "识别 FIFO/仲裁器等微架构"},
            {"skill": "explain_design_from_source", "why": "源码级解释模块功能"},
            {"skill": "find_interfaces", "why": "总线/接口协议识别"},
        ],
    },
    "protocol_latency": {
        "title": "握手 / 时延问题分析",
        "trigger": ["latency", "handshake", "ready", "valid", "时延"],
        "steps": [
            {"skill": "get_max_latency", "why": "最大时延统计"},
            {"skill": "check_handshake_stability", "why": "valid/ready 稳定性检查"},
            {"skill": "calculate_signal_duration", "why": "关键信号持续时长"},
            {"skill": "signal_event_report", "why": "事件报告汇总"},
        ],
    },
    "spec_to_sva": {
        "title": "Spec 到 SVA 断言自动生成 (DVCon 2025 趋势)",
        "trigger": ["spec", "sva", "assertion generation", "断言生成", "协议断言"],
        "steps": [
            {"skill": "sva_assertion_generation", "why": "方法论: Spec→SVA 推导, 误报>0 必须回退修订, liveness 标注 formal_only"},
            {"skill": "get_source_code", "why": "提取接口/模块 RTL 源码作为断言推导依据"},
            {"skill": "find_interfaces", "why": "识别协议接口与握手信号"},
            {"skill": "evaluate_assertion", "why": "在 FSDB 上评估候选 SVA 命中/误报"},
            {"skill": "get_assertion_statistics", "why": "以断言统计反馈迭代生成质量"},
        ],
    },
    "coverage_driven_stimulus": {
        "title": "覆盖率驱动智能激励 (DVCon 2025 趋势)",
        "trigger": ["coverage", "stimulus", "覆盖率", "激励", "hole"],
        "steps": [
            {"skill": "highlight_uncovered_items_in_source_view", "why": "源码视角定位未覆盖项/覆盖洞"},
            {"skill": "add_exclusions_for_uncovered_items", "why": "合法不可达项豁免, 不消耗迭代预算"},
            {"skill": "get_source_code", "why": "回溯覆盖洞相关 RTL 条件"},
            {"skill": "trace_signal", "why": "验证激励能否驱动覆盖洞信号"},
        ],
    },
    "rtl_code_review": {
        "title": "RTL 代码审查: 强制赋值/时钟/复位风险",
        "trigger": ["code review", "force", "release", "代码审查", "review"],
        "steps": [
            {"skill": "find_force_statements", "why": "枚举 testbench/RTL 中的 force 语句"},
            {"skill": "find_always_blocks", "why": "枚举时序/组合逻辑块, 检查时钟与复位驱动来源"},
            {"skill": "find_case_statements", "why": "检查 case 完整性风险 (latch/优先级)"},
            {"skill": "get_source_code", "why": "审查命中行的上下文代码"},
        ],
    },
    "uvm_verification_flow": {
        "title": "UVM 全流程 (8 阶段编排, 映射到真实技能面; loop-back 由 pipeline.py 执行)",
        "trigger": ["uvm", "testbench", "regression", "tb", "signoff"],
        "steps": [
            {"skill": "functional-verification", "why": "阶段1-2: testbench 架构 + vplan 条目 (QoR: 0 compile errors)"},
            {"skill": "generate_testbench", "why": "阶段3: 构建 (失败可 loop-back max 3x)"},
            {"skill": "check_uvm_compliance", "why": "阶段3 门禁: IEEE 1800.2-2020 静态合规"},
            {"skill": "run_simulation", "why": "阶段4-5: 定向+约束随机测试 (DUT bug → fix_request 升级)"},
            {"skill": "coverage_driven_stimulus", "why": "阶段6: 覆盖分析+智能激励 (gap → loop-back max 5x)"},
            {"skill": "formal-verification", "why": "阶段7: 形式化辅助 (协议/死锁/liveness)"},
            {"skill": "vplan_coverage_traceability", "why": "阶段8: vplan↔测试↔覆盖回链, 0 failure 才 signoff"},
        ],
    },
    "waveform_forensics": {
        "title": "波形取证与信号观测",
        "trigger": ["波形", "waveform", "fsdb", "加载波形", "看波形",
                    "add signal", "radix", "计数器", "counter", "占空比"],
        "steps": [
            {"skill": "load_fsdb", "why": "加载 FSDB 波形数据库"},
            {"skill": "get_active_fsdb", "why": "确认当前活动 FSDB"},
            {"skill": "set_active_fsdb", "why": "切换活动 FSDB"},
            {"skill": "add_signals", "why": "添加观测信号"},
            {"skill": "set_radix", "why": "设置显示进制/格式"},
            {"skill": "add_counter", "why": "添加信号计数显示"},
            {"skill": "active_temporal_trace", "why": "活动信号时序追踪"},
            {"skill": "get_signal_value_at_time", "why": "任意时刻信号取值"},
            {"skill": "get_first_value", "why": "信号初值"},
            {"skill": "get_last_value", "why": "信号终值"},
            {"skill": "get_signal_switching_statistics", "why": "占空比/高电平时长/翻转数"},
            {"skill": "signal_event_report", "why": "事件报告汇总"},
            {"skill": "open_waveform", "why": "在 Verdi GUI 打开波形 (缺失时返回可复制命令)"},
        ],
    },
    "timing_sequence": {
        "title": "信号时序/跳变/序列分析",
        "trigger": ["sequence", "序列", "transition", "跳变", "第n次", "首次",
                    "前后跳变", "值变化"],
        "steps": [
            {"skill": "detect_signal_sequence", "why": "检测信号序列模式"},
            {"skill": "detect_sequence_and_get_previous_transitions", "why": "序列检测并回取此前跳变"},
            {"skill": "detect_unknown_and_get_previous_or_next_transitions", "why": "X 出现前后跳变"},
            {"skill": "find_nth_transition_of_signal", "why": "第 N 次跳变定位"},
            {"skill": "find_signal_transition_to_value", "why": "跳到指定值的跳变点"},
            {"skill": "find_signal_value_change_event", "why": "值变化事件枚举"},
            {"skill": "search_signals_by_value_or_transition", "why": "按值/跳变检索信号"},
            {"skill": "calculate_signal_duration", "why": "电平持续时长"},
            {"skill": "get_max_latency", "why": "最大时延统计"},
        ],
    },
    "source_navigation": {
        "title": "源码/文本检索与跳转",
        "trigger": ["grep", "检索", "搜索", "search", "查找", "code pattern",
                    "read line", "上下文", "context"],
        "steps": [
            {"skill": "hierarchical_grep_search", "why": "层级化 grep 检索"},
            {"skill": "iterative_grep_search", "why": "迭代式检索 (逐步收窄)"},
            {"skill": "multi_pattern_search", "why": "多模式并行检索"},
            {"skill": "grep_with_context_expansion", "why": "上下文扩展检索"},
            {"skill": "find_code_pattern_in_module", "why": "模块内代码模式定位"},
            {"skill": "search_and_trace_definition", "why": "检索并追溯定义"},
            {"skill": "get_code_then_find", "why": "取码后再检索"},
            {"skill": "explore_then_find", "why": "探索结果内再检索"},
            {"skill": "search_in_source_code_result", "why": "在源码检索结果内二次检索"},
            {"skill": "search_in_exploration_result", "why": "在设计探索结果内二次检索"},
            {"skill": "read_specific_lines", "why": "读取指定行"},
            {"skill": "jump_to_source", "why": "跳转 RTL 源码"},
            {"skill": "get_source_code", "why": "取模块源码"},
        ],
    },
    "onesearch": {
        "title": "Verdi GUI/文档统一检索 (OneSearch)",
        "trigger": ["onesearch", "search menu", "search db", "gui 检索",
                    "文档检索", "dock", "菜单检索"],
        "steps": [
            {"skill": "onesearch_common", "why": "强制参数生成规则 (省略默认/互斥参数)"},
            {"skill": "search_db", "why": "数据库检索 (信号/模块)"},
            {"skill": "search_gui_content", "why": "GUI 窗口内容检索"},
            {"skill": "search_menu_command", "why": "菜单命令检索"},
        ],
    },
    "trace_workflows": {
        "title": "高级追踪工作流 (前向/两点/连通性)",
        "trigger": ["trace forward", "forward trace", "trace two", "two point",
                    "connectivity trace", "连通性追踪", "前向追踪", "两点追踪"],
        "steps": [
            {"skill": "trace_forward_workflow", "why": "信号前向扇出追踪"},
            {"skill": "trace_two_point_workflow", "why": "两点间路径追踪"},
            {"skill": "trace_connectivity_workflow", "why": "连通性路径追踪"},
        ],
    },
    "design_inventory": {
        "title": "设计对象清点 (模块/端口/实例/信号/参数)",
        "trigger": ["list", "清单", "列表", "inventory", "信号列表", "模块列表",
                    "实例", "参数", "scope", "port list", "信号过滤"],
        "steps": [
            {"skill": "check_if_design_loaded", "why": "确认设计已加载"},
            {"skill": "reload_design", "why": "必要时重载设计"},
            {"skill": "get_info", "why": "设计基本信息"},
            {"skill": "count_design_objects", "why": "对象数量统计"},
            {"skill": "list_module_definitions", "why": "模块定义列表"},
            {"skill": "list_ports_of_module", "why": "模块端口列表"},
            {"skill": "list_instances_in_hierarchy", "why": "层级实例列表"},
            {"skill": "list_signals", "why": "信号列表"},
            {"skill": "list_signals_in_scope", "why": "scope 内信号列表"},
            {"skill": "search_and_filter_signals", "why": "信号检索与条件过滤"},
            {"skill": "list_parameters_in_scope", "why": "scope 内参数列表"},
            {"skill": "search_scopes", "why": "检索 scope"},
            {"skill": "find_objects_by_wildcard", "why": "通配符对象检索"},
        ],
    },
    "rtl_structure": {
        "title": "RTL 结构检查 (always/case/task/function/断言)",
        "trigger": ["always", "case 语句", "case statement", "task/function",
                    "任务", "函数", "时序逻辑", "组合逻辑", "结构检查"],
        "steps": [
            {"skill": "find_always_blocks", "why": "枚举 always 块 (时序/组合逻辑)"},
            {"skill": "find_case_statements", "why": "枚举 case 语句 (检查 latch/优先级)"},
            {"skill": "find_tasks_and_functions", "why": "枚举 task/function"},
            {"skill": "find_assertions", "why": "枚举断言 (assert/assume/cover)"},
            {"skill": "find_force_statements", "why": "枚举 force 语句"},
            {"skill": "get_source_code", "why": "取命中位置上下文代码"},
        ],
    },
    "design_exploration_api": {
        "title": "Design/Netlist 对象 API 参考检索 (lang_/netlist_)",
        "trigger": ["netlist", "网表", "design api", "design object", "语言对象",
                    "pynpi", "npi", "接口绑定", "层次遍历", "structure exploration"],
        "steps": [
            {"skill": "netlist_connectivity", "why": "网表连通性 (路径/等价网/扇入扇出)"},
            {"skill": "netlist_port_query", "why": "网表端口查询"},
            {"skill": "netlist_named_object", "why": "网表命名对象查询"},
            {"skill": "netlist_class_types", "why": "网表对象类型"},
            {"skill": "netlist_bus_slice", "why": "总线切片处理"},
            {"skill": "netlist_scope_based_access", "why": "scope 访问模式"},
            {"skill": "netlist_traverse_from_file", "why": "按文件遍历网表"},
            {"skill": "netlist_traverse_hierarchy", "why": "网表层级遍历"},
            {"skill": "lang_class_signals", "why": "SV 信号类对象"},
            {"skill": "lang_class_nets", "why": "SV 线网类对象"},
            {"skill": "lang_class_instances", "why": "SV 实例类对象"},
            {"skill": "lang_class_scopes", "why": "SV scope 类对象"},
            {"skill": "lang_class_variables", "why": "SV 变量类对象"},
            {"skill": "lang_class_assertions", "why": "SV 断言类对象"},
            {"skill": "lang_class_statements", "why": "SV 语句类对象"},
            {"skill": "lang_child_modules", "why": "子模块查询"},
            {"skill": "lang_ports_query", "why": "端口查询"},
            {"skill": "lang_port_direction", "why": "端口方向过滤"},
            {"skill": "lang_definition_name", "why": "定义名解析"},
            {"skill": "lang_cousin_signal", "why": "同名异域信号 (cousin)"},
            {"skill": "lang_interface_binding", "why": "interface 绑定"},
            {"skill": "lang_logic_typespec", "why": "logic 类型规格"},
            {"skill": "lang_net_type_filter", "why": "线网类型过滤"},
            {"skill": "lang_struct_member", "why": "结构体成员访问"},
            {"skill": "lang_task_function", "why": "task/function 对象"},
            {"skill": "lang_full_hierarchy_traverse", "why": "全层级遍历"},
            {"skill": "lang_limited_scope_traverse", "why": "限定 scope 遍历"},
            {"skill": "lang_recursive_traverse", "why": "递归遍历"},
            {"skill": "lang_single_level_access", "why": "单层访问"},
            {"skill": "lang_scope_based_access", "why": "基于 scope 的访问"},
            {"skill": "lang_traverse_from_file", "why": "按文件遍历"},
            {"skill": "lang_wildcard_handling", "why": "通配符处理"},
            {"skill": "lang_wildcard_hierarchy", "why": "通配层级匹配"},
        ],
    },
    "testbench_generation": {
        "title": "生成 Testbench + 强制 UVM IEEE 1800.2-2020 合规检查",
        "trigger": [
            "生成 testbench", "生成testbench", "shengchen testbench",
            "generate testbench", "build testbench", "创建 testbench",
            "生成验证环境", "create testbench",
        ],
        "steps": [
            {"skill": "generate_testbench",
             "why": "从 UVM 1800.2-2020.3.1 标准模板生成完整验证环境"},
            {"skill": "check_uvm_compliance",
             "why": "强制检查: 生成后必须验证 IEEE 1800.2-2020 合规 (factory/config_db/TLM/clocking/objection), 不通过则报 ERR"},
        ],
    },
    "log_analysis": {
        "title": "EDA Log 迭代分析 (VCS/UVM/Verdi/LSF)",
        "trigger": ["分析log", "analyze log", "看log", "log analysis", "日志分析",
                    "分析日志", "check log", "parse log", "sim.log", "comp.log",
                    "log", "日志"],
        "steps": [
            {"skill": "analyze_eda_log", "why": "自动识别 log 类型, 提取结构化问题, 分类失败并推荐下一步 recipe"},
        ],
    },
    "simulation_run": {
        "title": "EDA 仿真运行 (VCS) + 工具环境发现",
        "trigger": ["仿真", "run vcs", "simulate", "跑仿真", "run simulation",
                    "编译仿真", "vcs 仿真", "跑测试"],
        "steps": [
            {"skill": "check_eda_tools", "why": "发现 VCS/Verdi/NPI 可用性 (modulefile 感知, 缺失时给 setup 指引)"},
            {"skill": "run_simulation", "why": "VCS 编译+仿真, 解析 UVM 报告 (PASS/FAIL/error/fatal)"},
        ],
    },
    # verif-agent-mcp (remote MCP server at $CHIP_AGENT_VERIF_AGENT_BIN,
    # 4 tools — run_vcs_simulation / diagnose_sim_log / analyze_coverage /
    # generate_uvm_env). Steps execute via the MCP adapter; degrade to
    # "no MCP server configured" without it, and the plan reports the
    # verif-agent launch command via chip_edatools.
    "verif_agent_flow": {
        "title": "VerifAgent 仿真→诊断→覆盖 闭环 (Synopsys verif-agent-mcp)",
        "trigger": ["覆盖分析", "coverage 分析", "analyze coverage", "urg 合并",
                    "仿真诊断", "诊断仿真", "coverage gap", "生成uvm环境",
                    "generate uvm env", "ipvgen"],
        "steps": [
            {"skill": "run_vcs_simulation", "why": "VCS 编译+仿真 (pass/fail/timeout + UVM_FATAL/ERROR 列表)"},
            {"skill": "diagnose_sim_log", "why": "失败时诊断: phase 时间线/objection 泄漏/断言失败根因摘要"},
            {"skill": "analyze_coverage", "why": "URG 合并覆盖目录, gap 按最差优先排序"},
        ],
    },

    # ------------------------------------------------------------------
    # digital-chip-design-agents 16-domain flows (vendored under digital/)
    # ------------------------------------------------------------------
    "architecture_evaluation": {
        "title": "架构评估: 微架构候选 / PPA 估算 / 风险评估",
        "trigger": ["microarchitecture", "micro-architecture", "架构评估",
                    "架构探索", "ppa estimate", "ppa 估算", "candidate architecture"],
        "steps": [{"skill": "architecture",
                   "why": "digital-agents: 微架构候选探索、PPA 估算与风险评估方法论"}],
    },
    "rtl_design_flow": {
        "title": "RTL 设计流: 编码标准/lint/CDC/综合检查",
        "trigger": ["write rtl", "rtl design flow", "rtl 设计", "写 rtl",
                    "cdc check", "cdc 检查", "lint rtl", "rtl lint"],
        "steps": [{"skill": "rtl-design",
                   "why": "digital-agents: 模块规划、编码标准、lint/CDC/综合检查闭环"}],
    },
    "formal_verification_flow": {
        "title": "形式验证 (FPV 性质证明 / LEC 等价性)",
        "trigger": ["formal verification", "formal property", "fpv", "lec",
                    "equivalence check", "形式验证", "等价性检查", "性质证明"],
        "steps": [{"skill": "formal-verification",
                   "why": "digital-agents: FPV 证明、LEC 等价、formal gap 收敛"}],
    },
    "logic_synthesis_flow": {
        "title": "逻辑综合: SDC/综合/LEC 网表验证",
        "trigger": ["logic synthesis", "run synthesis", "synthesis flow",
                    "dc_shell", "逻辑综合", "综合流程", "跑综合"],
        "steps": [{"skill": "logic-synthesis",
                   "why": "digital-agents: SDC 设置、综合运行、LEC 网表验证"}],
    },
    "dft_flow": {
        "title": "DFT: 扫描链插入 / ATPG / JTAG",
        "trigger": ["dft", "scan chain", "scan insertion", "atpg", "jtag",
                    "mbist", "扫描链", "可测性设计"],
        "steps": [{"skill": "dft",
                   "why": "digital-agents: DFT 计划、扫描插入、ATPG、JTAG 设置"}],
    },
    "sta_timing_flow": {
        "title": "静态时序分析: violation 分析 / ECO 闭环 / signoff",
        "trigger": ["sta", "static timing", "timing violation", "setup violation",
                    "hold violation", "wns", "tns", "eco timing",
                    "静态时序", "时序违例", "时序违规"],
        "steps": [{"skill": "sta",
                   "why": "digital-agents: STA 分析、ECO 收敛指导、时序 signoff"}],
    },
    "front_end_flow": {
        "title": "前端 RTL 相位: 架构→RTL→验证→形式→RTL 冻结",
        "trigger": ["前端", "front end", "frontend", "rtl 冻结", "rtl freeze",
                    "前端开发"],
        "steps": [{"skill": "architecture", "why": "规格→微架构/PPA 预算"},
                  {"skill": "rtl-design", "why": "RTL 编码 + lint/CDC/综合前检查"},
                  {"skill": "functional-verification", "why": "UVM 全流程直到覆盖率 100%"},
                  {"skill": "formal-verification", "why": "FPV 性质证明 + pre-gate LEC"},
                  {"skill": "flow_guide", "why": "前端→综合 handoff 判据 (lint=0/CDC=0/cov=100)"}],
    },
    "signoff_tapeout": {
        "title": "Signoff 签核: 多角 STA + DRC/LVS + 功耗/EM + tape-out 审查",
        "trigger": ["signoff", "签核", "tape out", "tapeout", "流片",
                    "drc lvs", "drc/lvs", "ir drop", "em 签核", "em signoff"],
        "steps": [{"skill": "sta", "why": "多角多模 setup/hold + exceptions 审查"},
                  {"skill": "physical-design", "why": "DRC/LVS/antenna 物理验证闭环"},
                  {"skill": "formal-verification", "why": "netlist≡GDS 门级等价"},
                  {"skill": "dft", "why": "ATPG/scan 覆盖率签核 (>=99%)"},
                  {"skill": "flow_guide", "why": "签核红线: 全部 gate 必须 measured-PASS, NOT RUN 不得上报 PASS"}],
    },
    "full_flow_rtl2gds": {
        "title": "RTL2GDS 全流程: 前端→综合→后端→Signoff 端到端",
        "trigger": ["rtl2gds", "rtl to gds", "全流程", "前端到后端",
                    "端到端", "full flow", "spec to tapeout", "spec 到流片"],
        "steps": [{"skill": "flow_guide", "why": "四相总览 + 每相 handoff 判据 + 跨相反馈环"},
                  {"skill": "design_state_pipeline", "why": "跨域闭环驱动 (fix_request/cap/divergence)"},
                  {"skill": "functional-verification", "why": "相位1: 前端验证闭环"},
                  {"skill": "logic-synthesis", "why": "相位2: 综合到门级网表"},
                  {"skill": "physical-design", "why": "相位3: 后端到 GDSII"},
                  {"skill": "sta", "why": "相位4: 多角时序签核"}],
    },
    "physical_design_flow": {
        "title": "物理设计: floorplan→placement→CTS→routing→signoff",
        "trigger": ["physical design", "floorplan", "placement", "cts",
                    "routing", "pd flow", "drc violation", "lvs",
                    "物理设计", "布局布线", "布线", "时钟树"],
        "steps": [{"skill": "physical-design",
                   "why": "digital-agents: 全 PD 流程与 DRC/LVS signoff 闭环"}],
    },
    "hls_flow": {
        "title": "高层综合: C/C++→RTL / directive 优化 / 协同仿真",
        "trigger": ["hls", "high-level synthesis", "c to rtl", "catapult", "stratus",
                    "catapult", "高层综合", "c转rtl"],
        "steps": [{"skill": "hls",
                   "why": "digital-agents: C/C++→RTL、directive 优化、协同仿真"}],
    },
    "soc_integration_flow": {
        "title": "SoC IP 集成: IP 资格审查 / 总线互连 / 芯片级仿真",
        "trigger": ["soc integration", "ip integration", "bus fabric",
                    "chip-level sim", "memory map", "soc 集成", "ip 集成",
                    "芯片级仿真"],
        "steps": [{"skill": "soc-integration",
                   "why": "digital-agents: IP 资格审查、总线配置、芯片级仿真"}],
    },
    "memory_ip_flow": {
        "title": "Memory IP: SRAM/RF/ROM 宏选型 / banking/ECC / repair",
        "trigger": ["memory ip", "sram selection", "sram compiler", "memory banking",
                    "ecc sram", "repair spare", "存储器选型", "memory ip 设计"],
        "steps": [{"skill": "memory-ip-design",
                   "why": "digital-agents: 宏选型、banking/ECC 架构、repair 分配、视图资格审查"}],
    },
    "compiler_toolchain_flow": {
        "title": "编译器工具链: LLVM/GCC 后端 / 汇编器 / 链接器",
        "trigger": ["compiler toolchain", "llvm backend", "gcc backend",
                    "custom isa", "assembler", "linker", "编译器工具链",
                    "自定义指令集"],
        "steps": [{"skill": "compiler-toolchain",
                   "why": "digital-agents: 自定义 ISA 的编译器后端/汇编/链接/运行时"}],
    },
    "embedded_firmware_flow": {
        "title": "嵌入式固件: BSP/HAL/RTOS 集成与验证",
        "trigger": ["embedded firmware", "bsp", "hal driver", "rtos",
                    "firmware validation", "嵌入式固件", "固件开发"],
        "steps": [{"skill": "embedded-firmware",
                   "why": "digital-agents: BSP、HAL 驱动、RTOS 集成、固件验证"}],
    },
    "fpga_emulation_flow": {
        "title": "FPGA 原型验证: ASIC→FPGA 移植 / 硬件 bring-up",
        "trigger": ["fpga emulation", "fpga prototype", "asic to fpga",
                    "fpga bring-up", "fpga 验证", "fpga 移植",
                    "原型验证"],
        "steps": [{"skill": "fpga-emulation",
                   "why": "digital-agents: ASIC→FPGA 移植、硬件 bring-up、原型软件验证"}],
    },
    "infrastructure_setup_flow": {
        "title": "EDA 环境基础设施: Synopsys/Cadence/Siemens 工具检测",
        "trigger": ["infrastructure setup", "vendor tool detection",
                "tool detection", "eda environment",
                    "环境搭建", "工具部署", "基础设施"],
        "steps": [{"skill": "infrastructure",
                   "why": "Synopsys/Cadence/Siemens 三厂商 detect-only 检测 + 非 EDA utilities"}],
    },
    "fix_request_pipeline": {
        "title": "验证↔RTL 闭环: fix_request 检测/调度/迭代上限/divergence",
        "trigger": ["fix request", "fix_request", "closed loop",
                    "pipeline orchestrator", "dut bug", "cross-domain",
                    "闭环", "修复请求", "跨域编排"],
        "steps": [{"skill": "pipeline-orchestration",
                   "why": "digital-agents: fix_request 协议权威方法论"},
                  {"skill": "design_state_pipeline",
                   "why": "代码化执行: 会话/迭代上限/divergence 检查/升级判定"}],
    },
    "memory_keeper_flow": {
        "title": "记忆维护: 经验检索/蒸馏/knowledge 沉淀",
        "trigger": ["memory keeper", "distill experience", "experience search",
                    "knowledge distill", "past experience", "记忆蒸馏",
                    "经验检索", "历史经验"],
        "steps": [{"skill": "memory-keeper",
                   "why": "digital-agents: experiences.jsonl→knowledge.md 蒸馏方法论"},
                  {"skill": "search_domain_memory",
                   "why": "TF-IDF 检索本域历史经验记录"}],
    },
    # ------------------------------------------------------------------
    # DVCon 2025/2026 论文语料转化 (DVCON_2025_2026_CORPUS.md 的调用映射)
    # 触发词避开既有宽词 (coverage/sva/uvm/testbench/regression 等) 以免
    # 被更早的 recipe 截胡; 论文出处见语料文件。
    # ------------------------------------------------------------------
    "fv_failure_debug": {
        "title": "形式化失败根因分析 (DVCon 2026 FVDebug: 因果图+LLM 取证+修复)",
        "trigger": ["counterexample", "cex debug", "反例分析", "根因定位",
                    "root cause 分析", "fv debug", "formal 失败根因",
                    "fvdebug", "因果链回溯"],
        "steps": [
            {"skill": "evaluate_assertion", "why": "取得失败断言/性质的状态与时间点 (因果图起点)"},
            {"skill": "explain_design_from_source", "why": "失败信号所在模块的源码级功能解释"},
            {"skill": "agentic_debug_workflow", "why": "多轮 plan-critique 交叉取证 (for-and-against 消偏)"},
            {"skill": "sva_assertion_generation", "why": "生成修复性断言并回验 (Fix Generator 等价物)"},
        ],
    },
    "agentic_formal_flow": {
        "title": "Agentic 形式化闭环 (DVCon 2025 Saarthi: coder/critic 反思循环)",
        "trigger": ["agentic formal", "formal 闭环", "saarthi",
                    "coder critic", "形式化多智能体", "sva 自动闭环"],
        "steps": [
            {"skill": "sva_assertion_generation", "why": "从 spec/RTL 生成候选 SVA (coder)"},
            {"skill": "assertion_feedback_refine", "why": "用命中率/误报率反馈迭代修订 (critic 循环)"},
            {"skill": "evaluate_assertion", "why": "在波形/设计上执行断言并收集结果"},
            {"skill": "formal-verification", "why": "digital-agents: FPV 性质证明与 LEC"},
        ],
    },
    "spec_rag_verification": {
        "title": "Spec-RAG 双记忆检索 (DVCon 2026 Samsung: STM/LTM 动态加权)",
        "trigger": ["spec rag", "hipporag", "知识图谱验证", "双记忆",
                    "memory network 验证", "rag 检索", "跨版本差异检索"],
        "steps": [
            {"skill": "search_domain_memory", "why": "LTM: 域 knowledge.md + 历史经验检索"},
            {"skill": "flow_guide", "why": "按 intent 定位研发相位与适用 recipe (决策逻辑)"},
            {"skill": "analyze_eda_log", "why": "STM: 当前日志/缺陷现场的结构化分类"},
        ],
    },
    "coverage_from_requirements": {
        "title": "NL 需求→功能覆盖代码生成 (DVCon Europe 2025 LLM coverage + 自动评估)",
        "trigger": ["nl2cov", "covgen", "coverpoint 生成",
                    "cross coverpoint 生成", "覆盖点自动生成"],
        "steps": [
            {"skill": "vplan_coverage_traceability", "why": "验证计划条目↔覆盖数据回链 (自动评估底座)"},
            {"skill": "coverage_driven_stimulus", "why": "覆盖洞→针对性激励, 关闭生成覆盖的欠激励场景"},
        ],
    },
    "regression_triage": {
        "title": "回归失败聚类/签名归并 (DVCon Europe 2025 ML triage: 12-43% TAT 缩减)",
        "trigger": ["失败聚类", "failure triage", "triage", "失败签名",
                    "signature 聚类", "相似失败定位", "回归聚类"],
        "steps": [
            {"skill": "analyze_eda_log", "why": "失败分类: failure_class + retry_strategy 签名"},
            {"skill": "search_domain_memory", "why": "检索同类历史失败与已验证解法 (签名复制)"},
            {"skill": "design_state_pipeline", "why": "重复失败进入 fix_request 闭环而非本地重试"},
        ],
    },
    "uvm_env_factory": {
        "title": "验证环境工厂 (DVCon Europe 2025 TBGen: 元数据驱动 + VIP 分类复用)",
        "trigger": ["tbgen", "验证环境工厂", "vip 复用", "ivc mvc",
                    "sysvc 分类", "testbench 工厂化"],
        "steps": [
            {"skill": "generate_testbench", "why": "从 UVM 1800.2-2020.3.1 模板生成标准环境骨架"},
            {"skill": "check_uvm_compliance", "why": "IEEE 1800.2-2020 13 类静态合规门禁"},
        ],
    },
}

def match_intent(text: str) -> list[str]:
    t = text.lower()
    scored: list[tuple[int, int, str]] = []
    for key, r in RECIPES.items():
        hits = [len(k) for k in r["trigger"] if _trigger_hit(k, t)]
        if hits:
            # primary: longest matched trigger; secondary: number of distinct
            # triggers hit (more hits = more specifically aimed intent).
            # e.g. "准备 signoff 流片" -> signoff_tapeout (signoff+流片) beats
            # uvm_verification_flow (signoff only)
            scored.append((max(hits), len(hits), key))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [k for _, _, k in scored] or ["design_onboarding"]


def _trigger_hit(trigger: str, lowered_text: str) -> bool:
    """Substring for phrases/CJK; word-boundary for short ASCII tokens.

    A bare short token like "x" or "dft" must match as a whole word —
    plain substring matching previously routed "mux issue" to x_prop_debug.
    """
    trig = trigger.lower()
    if len(trig) > 4 or not trig.isascii():
        return trig in lowered_text
    return re.search(rf"(?:^|[^a-z0-9_]){re.escape(trig)}(?:[^a-z0-9_]|$)",
                     lowered_text) is not None
