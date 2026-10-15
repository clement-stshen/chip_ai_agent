"""Deep chip development flow knowledge: 前端RTL → 综合 → 后端 → Signoff.

Codifies the industry 4-phase mainline (front-end RTL → synthesis →
back-end PD → signoff/tape-out) with, per phase:
  - participating domains (mapped to domain_flows.py engines)
  - stage chain, input/output artifacts
  - handoff (exit) criteria — a phase never hands off on an unmet gate
  - quality gates (QoR) and signoff thresholds
  - tool landscape (open-source + proprietary)
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
    tools_oss: list[str]
    tools_proprietary: list[str]
    pitfalls: list[str]


PHASES: dict[str, Phase] = {p.key: p for p in [
    Phase(
        key="front_end_rtl", position=1,
        title="前端 RTL (Front-end: architecture → RTL → verification)",
        domains=["architecture", "rtl-design", "verification", "formal"],
        stages=["spec/architecture", "RTL coding", "lint", "CDC/RDC",
                "functional verification (UVM)", "formal (FPV/LEC pre-gate)",
                "synth-check (pre-map estimate)", "RTL freeze"],
        inputs=["spec", "ISA/bus protocol", "PPA budget", "CDC constraints"],
        outputs=["frozen RTL (SystemVerilog)", "verification signoff report",
                 "CDC waiver list", "lint-clean report", "SVA assertions",
                 "synthesis-ready constraints (draft SDC)"],
        handoff=[
            "lint_errors == 0 (waived items documented)",
            "CDC/RDC violations unwaived == 0",
            "functional_coverage_pct == 100, regression_failures == 0",
            "unproven_p0_properties == 0 (formal)",
            "synth-check WNS >= -0.5ns and area <= 120% estimate",
        ],
        gates={"lint_errors": "== 0",
               "cdc_violations_unwaived": "== 0",
               "functional_coverage_pct": "== 100",
               "regression_failures": "== 0",
               "unproven_p0_properties": "== 0"},
        tools_oss=["verilator", "slang", "surelog", "iverilog", "cocotb", "sby"],
        tools_proprietary=["VCS", "Xcelium", "Questa", "SpyGlass", "JasperGold",
                           "VC Formal"],
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
                "LEC (RTL vs netlist)", "synthesis signoff"],
        inputs=["frozen RTL", "SDC", "target libs (.db/.lib)", "UPF (power intent)",
                "DFT spec (scan/atest/BIST)"],
        outputs=["gate-level netlist", "mapped SDC", "scan chain definition",
                 "timing/area/power QoR report", "LEC equivalence proof"],
        handoff=[
            "WNS >= 0 (or agreed negative-slack budget, e.g. >= -0.1ns for PD margin)",
            "LEC unmatched points == 0 (netlist ≡ RTL)",
            "unmapped cells == 0",
            "area <= budget; scan chain DRC clean; test coverage plan on track",
        ],
        gates={"wns_ns": ">= target (default 0)",
               "lec_unmatched_points": "== 0",
               "unmapped_cells": "== 0",
               "scan_drc_errors": "== 0"},
        tools_oss=["yosys", "abc", "surelog"],
        tools_proprietary=["Design Compiler", "Genus", "Fusion Compiler",
                           "TetraMAX (ATPG)", "Tessent", "Formality/Conformal LEC"],
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
                "ECO loops", "GDS out"],
        inputs=["gate-level netlist", "mapped SDC", "libs (.lib/.lef)",
                "tech file + RC parasitic models", "UPF", "IO/macros placement"],
        outputs=["GDSII", "DEF", "post-route netlist", "SPEF (parasitics)",
                 "CTS report", "DRC-clean layout", "IR/EM report"],
        handoff=[
            "post-route setup WNS >= 0 all corners",
            "hold WNS >= 0 (all corners)",
            "DRC violations == 0, LVS clean, antenna fixed",
            "core utilization <= target (default 85%), IR drop within budget",
        ],
        gates={"setup_wns_ns": ">= 0", "hold_wns_ns": ">= 0",
               "drc_violations": "== 0", "lvs_errors": "== 0",
               "antenna_violations": "== 0",
               "core_area_util_pct": "<= 85"},
        tools_oss=["openroad", "librelane", "klayout"],
        tools_proprietary=["Innovus", "ICC2", "Calibre (DRC/LVS)",
                           "RedHawk/Voltus (IR/EM)"],
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
        domains=["sta", "formal", "dft"],
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
            "DRC/LVS/antenna clean (or foundry-accepted waivers)",
            "IR drop / EM within foundry limits",
            "LEC netlist≡GDS clean; ATPG coverage >= 99%",
            "all signoff gates measured-PASS (never NOT RUN)",
        ],
        gates={"setup_wns_ns": ">= 0 all corners",
               "hold_wns_ps": ">= 0 all corners",
               "drc_violations": "== 0 (waived ok)",
               "lvs_errors": "== 0",
               "saf_coverage_pct": ">= 99"},
        tools_oss=["sta (OpenSTA)", "openroad", "klayout"],
        tools_proprietary=["PrimeTime (PX)", "Tempus", "Calibre",
                           "TetraMAX/Modus", "RedHawk/Voltus"],
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
            "tools": {"oss": p.tools_oss, "proprietary": p.tools_proprietary},
            "pitfalls": p.pitfalls,
            "feedbacks_from": [f.__dict__ for f in FEEDBACKS
                               if f.from_phase == p.key]}


def route_intent(intent: str) -> dict:
    """Map a natural-language intent to its phase + executable recipe."""
    t = intent.lower()
    best = None
    for kw, phase, recipe in INTENT_ROUTES:
        if kw in t and (best is None or len(kw) > len(best[0])):
            best = (kw, phase, recipe)
    if not best:
        return {"phase": None, "recipe": "design_onboarding",
                "note": "no phase keyword matched; default onboarding",
                "assistant_tools": _ASSISTANT_TOOLS["default"]}
    return {"matched_keyword": best[0], "phase": best[1],
            "phase_title": PHASES[best[1]].title,
            "recipe": best[2],
            "domains": PHASES[best[1]].domains,
            "handoff_criteria": PHASES[best[1]].handoff,
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
