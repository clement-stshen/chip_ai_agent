"""Deep chip development flow knowledge: 前端RTL → 综合 → 后端 → Signoff.

Codifies the industry 4-phase mainline (front-end RTL → synthesis →
back-end PD → signoff/tape-out) with, per phase:
  - participating domains (mapped to domain_flows.py engines)
  - stage chain, input/output artifacts
  - handoff (exit) criteria — a phase never hands off on an unmet gate
  - quality gates (QoR) and signoff thresholds
    - EDA tools restricted to Synopsys, Cadence, and Siemens
  - cross-phase feedback loops (who loops back to whom, and when)
  - classic pitfalls that cause downstream re-spins

Consumed by the chip_flow_guide MCP tool, the planner (intent → phase) and
the CHIP_FLOW_GUIDE.md human guide.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Feedback:
    when: str
    from_phase: str
    to_phase: str
    action: str


@dataclass(frozen=True)
class Phase:
    key: str
    title: str                     # bilingual title
    position: int                  # 1..4 mainline order
    domains: list[str]             # executable engines in domain_flows.py
    stages: list[str]
    inputs: list[str]
    outputs: list[str]
    handoff: list[str]             # exit criteria to next phase
    gates: dict[str, str]          # QoR gate -> criterion
    tools_synopsys: list[str]
    tools_cadence: list[str]
    tools_siemens: list[str]
    tools_utilities: list[str]
    pitfalls: list[str]


PHASES: dict[str, Phase] = {p.key: p for p in [
    Phase(
        key="front_end_rtl", position=1,
        title="前端 RTL (Front-end: architecture → RTL → verification)",
        domains=["architecture", "rtl-design", "verification", "formal"],
        stages=["spec/architecture", "RTL coding", "lint", "CDC/RDC",
            "functional verification (UVM)", "reset/UPF/X-prop checks",
            "formal (FPV/LEC pre-gate)",
                "synth-check (pre-map estimate)", "RTL freeze"],
        inputs=["spec", "ISA/bus protocol", "PPA budget", "CDC constraints"],
        outputs=["frozen RTL (SystemVerilog)", "verification signoff report",
                 "CDC waiver list", "lint-clean report", "SVA assertions",
                 "synthesis-ready constraints (draft SDC)"],
        handoff=[
            "lint_errors == 0 (waived items documented)",
            "CDC/RDC violations unwaived == 0",
            "functional_coverage_pct == 100, regression_failures == 0",
            "reset/CDC/UPF/X-prop and baseline regression checks pass",
            "unproven_p0_properties == 0 (formal)",
            "synth-check WNS >= -0.5ns and area <= 120% estimate",
        ],
        gates={"lint_errors": "== 0",
               "cdc_violations_unwaived": "== 0",
               "functional_coverage_pct": "== 100",
               "regression_failures": "== 0",
               "baseline_regression_failures": "== 0",
               "reset_regression_failures": "== 0",
               "cdc_rdc_violations_unwaived": "== 0",
               "low_power_assertion_failures": "== 0",
               "xprop_failures": "== 0",
               "unproven_p0_properties": "== 0"},
        tools_synopsys=['VCS', 'Verdi', 'SpyGlass', 'VC Formal'],
        tools_cadence=['Xcelium', 'JasperGold'],
        tools_siemens=['Questa', 'Questa CDC', 'Questa Formal'],
        tools_utilities=[],
        pitfalls=[
            "验证未闭环即交综合: 功能 bug 流到 netlist/GDS, 回改代价 x10",
            "CDC 检查只做不做 waiver 管控: 后端偶发亚稳态问题难定位",
            "RTL 用了综合不友好的结构 (latch 推断/异步复位风格不统一)",
            "综合前不做 synth-check: 面积/时序预算在 netlist 阶段才爆",
        ],
    ),
    Phase(
        key="synthesis", position=2,
        title="综合 (Synthesis: RTL → gate-level netlist)",
        domains=["synthesis", "dft"],
        stages=["constraint setup (SDC/lib/UPF)", "compile explore",
            "compile final", "DFT scan insertion", "netlist QC",
            "gate-level functional tests", "LEC (RTL vs netlist)",
            "synthesis signoff"],
        inputs=["frozen RTL", "SDC", "target libs (.db/.lib)", "UPF (power intent)",
                "DFT spec (scan/atest/BIST)"],
        outputs=["gate-level netlist", "mapped SDC", "scan chain definition",
                 "timing/area/power QoR report", "LEC equivalence proof"],
        handoff=[
            "WNS >= 0 (or agreed negative-slack budget, e.g. >= -0.1ns for PD margin)",
            "LEC unmatched points == 0 (netlist ≡ RTL)",
            "LEC equivalence and gate-level functional failures == PASS/0",
            "SDC/UPF errors, undefined clocks, unconstrained endpoints == 0",
            "gate-level functional failures == 0",
            "SDC errors / undefined clocks / unconstrained endpoints == 0",
            "unmapped cells == 0",
            "area <= budget; scan chain DRC clean; test coverage plan on track",
        ],
        gates={"wns_ns": ">= target (default 0)",
               "lec_unmatched_points": "== 0",
             "lec_equivalence_pass": "== true",
             "gate_level_functional_failures": "== 0",
                         "sdc_errors": "== 0", "upf_errors": "== 0",
                         "undefined_clocks": "== 0",
             "unconstrained_endpoints": "== 0",
               "unmapped_cells": "== 0",
               "scan_drc_errors": "== 0"},
        tools_synopsys=['Design Compiler', 'Fusion Compiler', 'StarRC'],
        tools_cadence=['Genus', 'Innovus', 'Voltus'],
        tools_siemens=['Calibre DRC/LVS'],
        tools_utilities=[],
        pitfalls=[
            "SDC 不完整/时钟未定义: 综合优化错误方向, 到 STA 才发现",
            "预留时序余量不足: PD 阶段线负载吃掉 slack, 被迫回 RTL 加流水",
            "DFT 插入滞后到后端: scan reorder 困难, coverage 上不去",
            "LEC 只对组合逻辑: 时钟域/复位语义差异漏检",
        ],
    ),
    Phase(
        key="back_end_pd", position=3,
        title="后端 (Back-end PD: netlist → GDSII)",
        domains=["pd", "memory-ip"],
        stages=["floorplan (die/core/IO/宏单元/电源网络)", "placement",
            "CTS (clock tree)", "routing", "timing/power/area optimization",
            "post-route netlist functional tests", "ECO loops", "GDS out"],
        inputs=["gate-level netlist", "mapped SDC", "libs (.lib/.lef)",
                "tech file + RC parasitic models", "UPF", "IO/macros placement"],
        outputs=["GDSII", "DEF", "post-route netlist", "SPEF (parasitics)",
                 "CTS report", "DRC-clean layout", "IR/EM report"],
        handoff=[
            "post-route setup WNS >= 0 all corners",
            "hold WNS >= 0 (all corners)",
            "DRC violations == 0, LVS clean, antenna fixed",
            "post-route netlist functional failures == 0; LEC equivalence PASS",
            "ECO equivalence PASS; total power <= budget; baseline regression failures == 0",
            "core utilization <= target (default 85%), IR drop within budget",
        ],
        # hold_wns_ps aligned with DOMAIN_FLOWS["pd"].signoff_gates (Step 20).
         gates={"setup_wns_ns": ">= 0", "hold_wns_ps": ">= 0",
             "lec_equivalence_pass": "== true",
             "eco_equivalence_pass": "== true",
             "post_route_functional_failures": "== 0",
             "baseline_regression_failures": "== 0",
             "total_power_mw": "<= budget",
               "drc_violations": "== 0", "lvs_errors": "== 0",
               "antenna_violations": "== 0",
               "core_area_util_pct": "<= 85"},
        tools_synopsys=['Fusion Compiler', 'ICC2', 'PrimeTime PX', 'StarRC'],
        tools_cadence=['Innovus', 'Tempus', 'Voltus'],
        tools_siemens=['Calibre DRC/LVS/XRC'],
        tools_utilities=[],
        pitfalls=[
            "floorplan 挤占优化空间: 宏单元/通道规划差 → 布线拥塞 → 时序死环",
            "CTS 前不做 skew/latency 预算: hold 修复量爆炸",
            "ECO 超过 2% cells 仍硬修: 应升级回综合/RTL 而非继续打补丁",
            "SPEF 缺失或过时: STA 用理想寄生, signoff 结果虚假",
        ],
    ),
    Phase(
        key="signoff", position=4,
        title="Signoff (签核: 多角 STA + 物理验证 + 功耗 + tape-out)",
        # pd included: physical verification (DRC/LVS/ANT) is a pd-domain engine.
        domains=["sta", "formal", "dft", "pd"],
        stages=["multi-corner multi-mode STA (setup/hold)",
                "timing exceptions review (false-path/multicycle)",
                "physical verification (DRC/LVS/ANT)",
                "power/EM/IR signoff", "gate-level equivalence (netlist vs GDS)",
                "DFT ATPG/scan signoff", "tape-out review"],
        inputs=["GDSII", "post-route netlist", "SPEF", "signoff SDC/corners",
                "UPF", "foundry rule deck"],
        outputs=["signed-off GDSII", "STA reports (all corners)",
                 "DRC/LVS waiver set", "ATPG patterns", "tape-out checklist"],
        handoff=[
            "setup/hold WNS/TNS meet target at ALL signoff corners/modes",
            "SDC valid, clocks defined, unconstrained endpoints == 0",
            "setup/hold violations == 0; ECO equivalence PASS when ECO applied",
            "DRC/LVS/antenna clean (or foundry-accepted waivers)",
            "IR drop / EM within foundry limits",
            "LEC netlist≡GDS clean; ATPG coverage >= 99%",
            "all signoff gates measured-PASS (never NOT RUN)",
        ],
         gates={"setup_wns_ns": ">= 0 all corners",
             "hold_wns_ps": ">= 0 all corners",
             "sdc_errors": "== 0", "undefined_clocks": "== 0",
             "unconstrained_endpoints": "== 0",
             "setup_violations": "== 0", "hold_violations": "== 0",
             "eco_equivalence_pass": "== true",
               "drc_violations": "== 0 (waived ok)",
               "lvs_errors": "== 0",
               "saf_coverage_pct": ">= 99"},
        tools_synopsys=['PrimeTime PX', 'StarRC', 'VC Formal', 'VCS'],
        tools_cadence=['Tempus', 'Voltus', 'JasperGold', 'Conformal LEC'],
        tools_siemens=['Calibre DRC/LVS/XRC', 'Questa'],
        tools_utilities=[],
        pitfalls=[
            "只签单角/单模: 最差角 setup 或 hold 漏检, 流片后才发现",
            "exception 滥用 (false-path 掩盖真实路径)",
            "waiver 无 traceability: foundry audit 退回",
            "把 NOT RUN 的 gate 当 PASS 上报 (reporting contract 红线)",
        ],
    ),
]}

# cross-phase feedback loops — the real reason flows iterate
FEEDBACKS: list[Feedback] = [
    Feedback("functional bug found in verification/formal", "front_end_rtl",
             "front_end_rtl", "fix_request closed loop: RTL fix → re-verify (cap 3x, divergence check)"),
    Feedback("synthesis WNS/area cannot converge", "synthesis",
             "front_end_rtl", "RTL restructure: pipeline/retiming/architecture change"),
    Feedback("LEC RTL≡netlist fails", "synthesis", "synthesis",
             "fix synthesis constraints/scripts, re-compile (max 3x)"),
    Feedback("post-route setup/hold violation", "back_end_pd",
             "back_end_pd", "ECO → re-route → re-STA (max 10x total)"),
    Feedback("ECO > 2% cells", "back_end_pd", "synthesis",
             "escalate: re-synthesize instead of endless patches (max 1x back)"),
    Feedback("DRC/LVS/antenna fail at signoff", "signoff",
             "back_end_pd", "routing/floorplan fix loop (max 2x)"),
    Feedback("IR/EM violation", "signoff", "back_end_pd",
             "power-network rework → power optimization (max 1x)"),
    Feedback("STA worst-corner fail after ECO cap", "signoff",
             "front_end_rtl", "timing escalation chain: PD→synthesis→RTL"),
]

# natural-language intent routing (zh + en) to phases and executable recipes
INTENT_ROUTES: list[tuple[str, str, str]] = [
    # keywords, phase, recipe (chip_ai_agent)
    ("前端", "front_end_rtl", "rtl_design_flow"),
    ("front end", "front_end_rtl", "rtl_design_flow"),
    ("frontend", "front_end_rtl", "rtl_design_flow"),
    ("rtl design", "front_end_rtl", "rtl_design_flow"),
    ("写 rtl", "front_end_rtl", "rtl_design_flow"),
    ("uvm", "front_end_rtl", "uvm_verification_flow"),
    ("验证环境", "front_end_rtl", "uvm_verification_flow"),
    ("cdc", "front_end_rtl", "rtl_design_flow"),
    ("综合", "synthesis", "logic_synthesis_flow"),
    ("synthesis", "synthesis", "logic_synthesis_flow"),
    ("dc_shell", "synthesis", "logic_synthesis_flow"),
    ("门级网表", "synthesis", "logic_synthesis_flow"),
    ("netlist", "synthesis", "logic_synthesis_flow"),
    ("dft", "synthesis", "dft_flow"),
    ("scan", "synthesis", "dft_flow"),
    ("后端", "back_end_pd", "physical_design_flow"),
    ("back end", "back_end_pd", "physical_design_flow"),
    ("backend", "back_end_pd", "physical_design_flow"),
    ("物理设计", "back_end_pd", "physical_design_flow"),
    ("physical design", "back_end_pd", "physical_design_flow"),
    ("布局布线", "back_end_pd", "physical_design_flow"),
    ("place and route", "back_end_pd", "physical_design_flow"),
    ("pnr", "back_end_pd", "physical_design_flow"),
    ("floorplan", "back_end_pd", "physical_design_flow"),
    ("cts", "back_end_pd", "physical_design_flow"),
    ("时钟树", "back_end_pd", "physical_design_flow"),
    ("gds", "back_end_pd", "physical_design_flow"),
    ("signoff", "signoff", "signoff_tapeout"),
    ("签核", "signoff", "signoff_tapeout"),
    ("tape out", "signoff", "signoff_tapeout"),
    ("tapeout", "signoff", "signoff_tapeout"),
    ("流片", "signoff", "signoff_tapeout"),
    ("drc", "signoff", "signoff_tapeout"),
    ("lvs", "signoff", "signoff_tapeout"),
    ("sta", "signoff", "sta_timing_flow"),
    ("时序签核", "signoff", "sta_timing_flow"),
    ("timing violation", "signoff", "sta_timing_flow"),
    ("rtl2gds", "front_end_rtl", "full_flow_rtl2gds"),
    ("rtl to gds", "front_end_rtl", "full_flow_rtl2gds"),
    ("全流程", "front_end_rtl", "full_flow_rtl2gds"),
    ("前端到后端", "front_end_rtl", "full_flow_rtl2gds"),
    ("端到端", "front_end_rtl", "full_flow_rtl2gds"),
]


def overview() -> list[dict]:
    return [{"position": p.position, "key": p.key, "title": p.title,
             "domains": p.domains, "stages": p.stages,
             "handoff": p.handoff}
            for p in sorted(PHASES.values(), key=lambda x: x.position)]


def phase_detail(key: str) -> dict:
    try:
        p = PHASES[key]
    except KeyError:
        raise ValueError(f"unknown phase: {key!r} "
                         f"(valid: {', '.join(PHASES)})") from None
    return {"key": p.key, "title": p.title, "position": p.position,
            "domains": p.domains, "stages": p.stages,
            "inputs": p.inputs, "outputs": p.outputs,
            "handoff_criteria": p.handoff, "gates": p.gates,
            "tools": {"synopsys": p.tools_synopsys,
                      "cadence": p.tools_cadence,
                      "siemens": p.tools_siemens,
                      "utilities": p.tools_utilities},
            "pitfalls": p.pitfalls,
            "feedbacks_from": [f.__dict__ for f in FEEDBACKS
                               if f.from_phase == p.key]}


def route_intent(intent: str) -> dict:
    """Map a natural-language intent to its phase + executable recipe."""
    t = intent.lower()
    hits = []
    for kw, phase, recipe in INTENT_ROUTES:
        if kw in t:
            hits.append((kw, phase, recipe))
    best = max(hits, key=lambda h: len(h[0]), default=None)
    alternatives = [
        {"keyword": kw, "phase": phase, "recipe": recipe}
        for kw, phase, recipe in sorted(hits, key=lambda h: -len(h[0]))
        if best is None or kw != best[0]
    ]
    if not best:
        return {"phase": None, "recipe": "design_onboarding",
                "note": "no phase keyword matched; default onboarding",
                "assistant_tools": _ASSISTANT_TOOLS["default"]}
    return {"matched_keyword": best[0], "phase": best[1],
            "phase_title": PHASES[best[1]].title,
            "recipe": best[2],
            "domains": PHASES[best[1]].domains,
            "handoff_criteria": PHASES[best[1]].handoff,
            "alternatives": alternatives,
            "assistant_tools": _ASSISTANT_TOOLS.get(
                best[1], _ASSISTANT_TOOLS["default"])}


# cross-tool linkage: per-phase recommendations into the auxiliary
# retrieval tools integrated from /tools/Synopsys/temp (UG vector docs,
# NPI C-API index, golden example library).
_ASSISTANT_TOOLS: dict[str, list[str]] = {
    "default": ["chip_agent_skills", "chip_ug_search"],
    "front_end_rtl": [
        "chip_examples",          # 黄金 UVM TB 范例 (uart_example)
        "chip_ug_search",         # UVM/VCS 用户文档向量检索
        "chip_npi",               # HDL/FSDB C API 辅助脚本
    ],
    "synthesis": [
        "chip_ug_search",         # DC/综合流程文档
        "chip_npi",               # netlist (npi_nl) / UPF 接口
    ],
    "back_end_pd": [
        "chip_ug_search",         # PD/Innovus/ICC2 文档
        "chip_npi",               # npi_nl/npi_pw 接口
    ],
    "signoff": [
        "chip_ug_search",         # STA/物理验证/功耗签核文档
        "chip_npi",               # npi_cov/npi_cv 覆盖率数据库接口
        "chip_examples",          # 签核报告/脚本范例
    ],
}


# ---------------------------------------------------------------------------
# capability map: 资深芯片工程师的七项核心能力 ↔ agent 机制 ↔ 工具面
# (Step 8) — spec/架构/EDA/报告/根因/回归保护/PPA+物理收敛
# ---------------------------------------------------------------------------
CAPABILITY_MAP: list[dict] = [
    {"capability": "理解规格 (spec)",
     "agent_mechanism": [
         "plan() intent→domain→recipe 映射 + 域 knowledge 注入",
         "chip_ug_search 向量检索官方手册 (VCS/Verdi UG)",
         "chip_dvcon_search 检索 DVCon 2025/2026 论文方法论 (abstract/method/conclusion, track tag 过滤)",
         "domain_flows 每域 inputs/handoff criteria 显式编码规格要求"],
     "tools": ["chip_agent_plan", "chip_ug_search", "chip_dvcon_search",
               "chip_domain_flows"]},
    {"capability": "规划架构",
     "agent_mechanism": [
         "四相主线 pipeline_plan (architecture→…→sta)",
         "反馈环定义了架构级回退路径 (WNS 不收敛→RTL restructure)",
         "checkpoint 人工门: 架构决策不静默通过"],
     "tools": ["chip_flow_guide(op=route)", "chip_design_pipeline"]},
    {"capability": "使用 EDA 工具",
     "agent_mechanism": [
         "三厂商工具探测 (Synopsys/Cadence/Siemens, chip_edatools)",
         "每域 Synopsys/Cadence/Siemens 三厂商工具路由表",
         "NPI C API 索引 (24 头文件/506 API) 辅助脚本生成"],
     "tools": ["chip_edatools", "chip_run_simulation",
               "chip_npi"]},
    {"capability": "阅读报告",
     "agent_mechanism": [
         "eda_log_analyzer: VCS/UVM/Verdi log 结构化解析 (两行式 Error 定位)",
         "RTL/gate-level/post-route 与 STA/SDC 报告进入 measured-PASS 门, NOT RUN≠PASS",
         "chip_qor_trends 跨 run QoR 趋势/回归检测"],
     "tools": ["chip_analyze_eda_log", "chip_qor_trends"]},
    {"capability": "定位根因",
     "agent_mechanism": [
         "failure_taxonomy 分类 (timing/functional/coverage/tool_error…)",
         "waveform_causal_diagnosis 技能: 从现象时刻沿驱动链回溯",
         "loop_back 表编码 '什么失败→回到哪一步修' 的因果规则"],
     "tools": ["chip_agent_skills", "chip_open_waveform",
               "chip_analyze_eda_log"]},
    {"capability": "保护已有正确行为",
     "agent_mechanism": [
         "fix_request 闭环: DUT bug→escalate→RTL fix→re-verify (cap 3x)",
         "RTL reference/RTL-netlist/post-route ECO LEC、reset/CDC/UPF/X-prop 均为 measured-PASS 门",
         "门级与 post-route 功能检查、baseline regression 门 + 经验记忆复用"],
     "tools": ["chip_design_pipeline", "chip_agent_recall"]},
    {"capability": "推动 PPA + 物理规则收敛",
     "agent_mechanism": [
         "每域 signoff_gates: WNS/TNS/IR/EM/DRC/LVS/coverage 阈值",
         "loop cap 上限 + escalation 链 (PD→synthesis→RTL) 防无限迭代",
         "跨域收敛: 综合 QoR 不达标回退架构, signoff 失败回退 PD"],
     "tools": ["chip_design_pipeline", "chip_domain_flows"]},
]


def capabilities() -> list[dict]:
    """资深工程师能力 ↔ agent 机制 ↔ 工具 (供 chip_flow_guide op=capabilities)."""
    return CAPABILITY_MAP


# ---------------------------------------------------------------------------
# post-RTL verification depth checklist (Step 24): RTL Simulation 只是起点;
# 下表把"RTL 之后每一步可能悄悄破坏功能"的工业检查项映射到域引擎的
# 实际 signoff gate (audit 测试强制每个 gate 真实存在)。
# ---------------------------------------------------------------------------
POST_RTL_CHECKLIST: list[dict] = [
    {"id": "pre_post_synth_lec",
     "concern": "综合前后逻辑等价性 (LEC)",
     "why": "综合脚本/约束/库 mismatch 会在 RTL 无感的情况下改变功能",
     "domains": ["synthesis", "formal"],
     "gates": {"synthesis": ["lec_unmatched_points", "lec_equivalence_pass"],
               "formal": ["lec_unmatched_points"]},
     "agent_check": "DomainFlowRunner(synthesis/formal) 以 measured-PASS 门校验 LEC 结果; 未运行=NOT RUN 不放行",
     "tools": ["chip_design_pipeline", "chip_domain_flows"]},
    {"id": "gl_post_route_functional",
     "concern": "Gate-level / post-route netlist 关键功能检查",
     "why": "netlist 时序/负载/SDF 语义与 RTL 不同, RTL 回归通过不代表门级通过",
     "domains": ["synthesis", "pd"],
     "gates": {"synthesis": ["gate_level_functional_failures"],
               "pd": ["post_route_functional_failures"]},
     "agent_check": "gate_level_functional_failures==0 与 post_route_functional_failures==0 均为 signoff 门, 失败按 functional taxonomy loop/escalate",
     "tools": ["chip_design_pipeline", "chip_run_simulation"]},
    {"id": "sdc_clock_constraints",
     "concern": "SDC 与时钟约束正确性",
     "why": "错误/缺失约束会产生'假 WNS 闭合', 时序报告本身不可信",
     "domains": ["synthesis", "sta"],
     "gates": {"synthesis": ["sdc_errors", "undefined_clocks",
                             "unconstrained_endpoints"],
               "sta": ["sdc_errors", "undefined_clocks",
                       "unconstrained_endpoints"]},
     "agent_check": "约束合法性先于 WNS 检查: sdc_errors/undefined_clocks/unconstrained_endpoints 全 PASS 后才解读 WNS",
     "tools": ["chip_design_pipeline", "chip_qor_trends"]},
    {"id": "setup_hold_closure",
     "concern": "Setup / Hold 真正闭合",
     "why": "单 corner 或单 看 WNS 会漏 hold/多 corner 收敛问题",
     "domains": ["sta", "pd"],
     "gates": {"sta": ["setup_wns_ns", "hold_wns_ps", "setup_tns_ps",
                       "hold_tns_ps", "setup_violations", "hold_violations"],
               "pd": ["setup_wns_ns", "hold_wns_ps", "setup_tns_ps"]},
     "agent_check": "setup+hold 的 WNS/TNS/violations 三层门同时非负/为零, 一项不满足即 escalate",
     "tools": ["chip_design_pipeline", "chip_analyze_eda_log"]},
    {"id": "reset_cdc_lp_xprop",
     "concern": "Reset / CDC / 低功耗 / X 传播引入的新问题",
     "why": "跨时钟/电源域与复位序列的 bug 只在结构级检查和专用仿真中出现",
         "domains": ["rtl-design", "verification", "synthesis"],
         "gates": {"rtl-design": ["cdc_violations_unwaived"],
               "synthesis": ["upf_errors"],
               "verification": ["reset_regression_failures",
                    "cdc_rdc_violations_unwaived",
                    "low_power_assertion_failures",
                    "xprop_failures"]},
     "agent_check": "CDC/RDC/低功耗断言/X-prop/复位回归各有独立门, 不可互相替代; unwaived 计数必须为 0",
     "tools": ["chip_design_pipeline", "chip_agent_skills"]},
    {"id": "eco_equivalence",
     "concern": "ECO 后保持功能等价",
     "why": "时序 ECO 改网表连接/单元, 必须证明没有破坏功能",
         "domains": ["sta", "pd"],
         "gates": {"sta": ["eco_equivalence_pass"],
               "pd": ["eco_equivalence_pass"]},
         "agent_check": "STA/PD 中每个 ECO 迭代后 eco_equivalence_pass 必须 measured-PASS; 无 ECO 必须记录有证据的 measured N/A, 否则不进入 tape-out",
     "tools": ["chip_design_pipeline"]},
    {"id": "ppa_regression_guard",
     "concern": "PPA 优化不破坏已有回归结果",
     "why": "重timing/面积/功耗 的 netlist 改动可能引入功能回归",
     "domains": ["verification", "pd"],
     "gates": {"verification": ["regression_failures",
                                "baseline_regression_failures"],
             "pd": ["baseline_regression_failures", "total_power_mw",
                 "core_area_util_pct",
                      "ir_drop_mv", "em_violations"]},
     "agent_check": "PPA 优化后强制重跑回归 (regression/baseline 双门); QoR 趋势 (chip_qor_trends) 检测跨 run 漂移",
     "tools": ["chip_design_pipeline", "chip_qor_trends"]},
]


def post_rtl_checklist() -> list[dict]:
    """供 chip_flow_guide op=post_rtl_checklist: 深度签核检查项 ↔ 域门映射.

    每项附 dvcon_papers: 检查项 ↔ DVCon 2025/2026 论文方法双向链接
    (best-effort: 语料索引不可用时安静跳过, 不影响 checklist 本体).
    """
    query_by_id = {
        "pre_post_synth_lec": "equivalence checking ECO",
        "gl_post_route_functional": "X-propagation gate level regression",
        "sdc_clock_constraints": "SDC coverage closure constraints",
        "setup_hold_closure": "SDC coverage closure timing constraints",
        "reset_cdc_lp_xprop": "low-power verification CDC reset",
        "eco_equivalence": "equivalence checking ECO",
        "ppa_regression_guard": "agentic regression management",
    }
    items = [dict(it) for it in POST_RTL_CHECKLIST]
    try:
        from . import dvcon_index
        for it in items:
            q = query_by_id.get(it["id"])
            if not q:
                continue
            sr = dvcon_index.search(q, top_k=2)
            hits = sr.get("hits", [])
            if hits:
                it["dvcon_papers"] = [
                    {"title": h["title"], "authors": h["authors"],
                     "year": h["year"], "query": q}
                    for h in hits if h["kind"] == "abstract"]
    except Exception:
        pass
    return items
