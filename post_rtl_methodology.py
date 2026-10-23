"""Post-RTL verification methodology decision layer.

RTL simulation alone is insufficient sign-off. This module provides structured
methodology for the 7-stage post-RTL verification flow:

  1. LEC        - post-synthesis logical equivalence checking
  2. GL-sim     - gate-level / post-route netlist functional verification
  3. SDC        - SDC & clock constraint correctness validation
  4. STA        - setup / hold timing closure across all corners
  5. Struct     - reset, CDC, low-power (UPF), X-propagation
  6. ECO        - post-ECO functional equivalence
  7. PPA-guard  - PPA optimization regression protection

Each stage provides: decision tree, EDA command skeletons, report interpretation,
root-cause patterns, pitfalls, handoff criteria, RAG queries, and tool chains.
Cross-stage orchestration tracks multi-dimensional convergence (function ×
timing × power × area × physical).
"""

from __future__ import annotations

import re
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------
STAGES = OrderedDict()

STAGES["lec"] = {
    "id": "pre_post_synth_lec",
    "concern": "综合前后逻辑等价性 (LEC)",
    "why": "综合脚本/约束/库 mismatch 会在 RTL 无感的情况下改变功能",
    "inputs": ["RTL (golden)", "post-synthesis netlist (revised)", "SDC", "standard cell library (.lib)"],
    "outputs": ["LEC report (matched/unmatched/confirm/unconfirm)", "equivalence PASS/FAIL"],
    "decision": "Run LEC immediately after synthesis (Design Compiler → Formality/Conformal). "
                "If unmatched points > 0, debug mapping before proceeding to GL-sim. "
                "If LEC fails, fix synthesis constraints — do NOT proceed with a broken netlist.",
    "tool_commands": [
        "# Formality (Synopsys)",
        "fm_shell -f lec_run.tcl",
        "# lec_run.tcl:",
        "  set_app_var synopsys_auto_setup true",
        "  read_sverilog -r {rtl_files}",
        "  set_top r:/WORK/top_module",
        "  read_db target_lib.lib",
        "  read_verilog -i netlist.v",
        "  set_top i:/WORK/top_module",
        "  match   # auto-match + report unmatched",
        "  verify  # sequential equivalence check",
    ],
    "report_interpretation": [
        "Matching: matched_points should equal total compare points; unmatched > 0 = FAIL",
        "Verification: 'Verification SUCCEEDED' = PASS; 'FAILED' = functional divergence",
        "Passing points vs failing points: focus on first failing point",
        "Unmatched DFF/cells: usually missing dont_touch or name preservation issue",
    ],
    "root_cause_patterns": [
        "Unmatched DFFs → missing set_dont_touch on clock gating cells",
        "Unmatched combinational → name mapping failure (synthesis renamed signals)",
        "Verification FAIL at specific compare point → synthesis optimization changed logic",
        "Missing black boxes → library path incorrect or IBIS missing",
    ],
    "pitfalls": [
        "Forgetting to set synopsys_auto_setup true → SDC constraint mismatches",
        "Not specifying black boxes for memories/analog macros → false failures",
        "Running LEC only on top module, skipping sub-module LEC → hidden mismatches",
        "Ignoring unmatched points count → partial equivalence only",
    ],
    "handoff": {
        "gate": "lec_equivalence_pass == true AND lec_unmatched_points == 0",
        "next_stage": "gl_post_route_functional",
        "if_fail": "Fix synthesis script/SDC/library, re-synthesize, re-run LEC",
    },
    "rag_queries": {
        "manual": "logical equivalence checking LEC formal verification",
        "dvcon_tag": "signoff",
        "dvcon_query": "equivalence checking ECO formal",
    },
    "next_tools": [
        "chip_design_pipeline(op=run, domain=synthesis)",
        "chip_analyze_eda_log(kind=formality)",
        "chip_rag_search(query='LEC unmatched points debugging', backends=['manual_search','dvcon_index'])",
    ],
}

STAGES["gl_post_route_functional"] = {
    "id": "gl_post_route_functional",
    "concern": "Gate-level / post-route netlist 关键功能检查",
    "why": "netlist 时序/负载/SDF 语义与 RTL 不同, RTL 回归通过不代表门级通过",
    "inputs": ["post-synthesis/post-route netlist", "SDF (standard delay format)", "testbench", "SDC", "library models"],
    "outputs": ["GL regression PASS/FAIL", "SDF timing violation count", "functional mismatch list"],
    "decision": "After LEC PASS, run gate-level simulation with SDF back-annotation. "
                "If SDF annotation errors > 0, check SDF version/netlist version match. "
                "If functional mismatches, compare with RTL sim traces to isolate.",
    "tool_commands": [
        "# VCS gate-level simulation",
        "vcs -full64 netlist.v \\",
        "    -v target_lib.v \\",
        "    +neg_tchk +sdf_verbose \\",
        "    -sdf max:top_module:top_module.sdf \\",
        "    +delay_mode_zero \\  # for functional-only (no timing)",
        "    tb_top.v",
        "",
        "# For timing-aware (post-route):",
        "  -sdf min:typ:max:top_module:top_module.sdf",
        "  +overlap +notimingcheck  # debug mode",
    ],
    "report_interpretation": [
        "SDF annotation: 'WARNING: timing check ... no SDF' = missing annotation",
        "Timing violation: SETUP/HOLD violations in gate-level = STA not converged",
        "X-propagation: X on Q output of DFF = uninitialized/reset issue",
        "Functional mismatch: compare RTL vs GL waveform traces for first divergent cycle",
    ],
    "root_cause_patterns": [
        "X on sequential outputs → missing reset or reset not reaching all flops",
        "SETUP violations → STA hold fix not applied or wrong SDF corner",
        "HOLD violations → buffer not inserted or min-delay path missed",
        "Functional mismatch only in GL → combinational loop or async path",
    ],
    "pitfalls": [
        "Using +delay_mode_zero for sign-off (should use real SDF for final)",
        "Not enabling +neg_tchk → negative timing check suppressed",
        "Missing library timing models (SDF references cells not in library)",
        "Running GL-sim without LEC → garbage-in garbage-out",
    ],
    "handoff": {
        "gate": "gate_level_functional_failures == 0 AND sdf_annotation_errors == 0",
        "next_stage": "sdc_clock_constraints",
        "if_fail": "Compare RTL vs GL traces, isolate first divergent cycle, debug netlist",
    },
    "rag_queries": {
        "manual": "gate-level netlist simulation SDF back-annotation VCS",
        "dvcon_tag": "signoff",
        "dvcon_query": "gate level regression X-propagation",
    },
    "next_tools": [
        "chip_run_simulation(extra_args=['-sdf', 'max:top:top.sdf'])",
        "chip_analyze_eda_log(kind=vcs)",
        "chip_open_waveform(fsdb='gl_sim.fsdb')",
    ],
}

STAGES["sdc_clock_constraints"] = {
    "id": "sdc_clock_constraints",
    "concern": "SDC 与时钟约束正确性",
    "why": "错误/缺失约束会产生'假 WNS 闭合', 时序报告本身不可信",
    "inputs": ["SDC file", "netlist", "clock specification", "IO timing requirements"],
    "outputs": ["SDC lint report", "undefined clock list", "unconstrained endpoint count", "constraint coverage %"],
    "decision": "Before interpreting ANY STA timing report, validate SDC. "
                "If undefined_clocks > 0 or unconstrained_endpoints > 0, the WNS/TNS numbers "
                "are UNTRUSTWORTHY — fix constraints first, then re-run STA.",
    "tool_commands": [
        "# PrimeTime SDC validation",
        "pt_shell>",
        "  read_sdc design.sdc",
        "  report_clock -skew         # clock definition check",
        "  report_timing_requirements # missing constraints",
        "  check_timing               # comprehensive lint",
        "  report_exceptions          # false paths / multicycle",
        "",
        "# SpyGlass SDC lint (more comprehensive)",
        "spyglass -project sdc_lint.prj -goal sdc_lint",
    ],
    "report_interpretation": [
        "check_timing: 'no_clock' endpoints = unconstrained, must be 0 for sign-off",
        "check_timing: 'unconstrained_endpoints' = output ports without set_output_delay",
        "report_clock: verify period, waveform, sources match spec",
        "report_exceptions: verify false_path/multicycle are intentional, not accidental",
        "SDC lint warnings about cross-domain → possible missing set_clock_groups",
    ],
    "root_cause_patterns": [
        "no_clock on endpoints → missing create_clock or derived clock not propagated",
        "unconstrained_endpoints → missing set_output_delay on output ports",
        "False path between clock domains → missing set_clock_groups -asynchronous",
        "Setup/hold contradict → check if multicycle path is missing",
        "Generated clock not found → missing create_generated_clock",
    ],
    "pitfalls": [
        "Assuming WNS is correct without check_timing → false convergence",
        "Setting false_path on CDC paths without proper clock group definition",
        "Missing set_input_delay/set_output_delay on top-level ports",
        "Not checking generated clock relationships (divide-by-N clocks)",
        "Ignoring unconstrained paths because 'we always did it this way'",
    ],
    "handoff": {
        "gate": "sdc_errors == 0 AND undefined_clocks == 0 AND unconstrained_endpoints == 0",
        "next_stage": "setup_hold_closure",
        "if_fail": "Fix SDC, re-run STA, THEN interpret timing results",
    },
    "rag_queries": {
        "manual": "SDC clock constraint setup hold input delay output delay PrimeTime",
        "dvcon_tag": "timing",
        "dvcon_query": "SDC coverage closure ML timing constraints",
    },
    "next_tools": [
        "chip_rag_search(query='SDC clock constraint check_timing', backends=['manual_search'])",
        "chip_analyze_eda_log(kind=sta)",
        "chip_qor_trends(design=top_module, domain=sta)",
    ],
}

STAGES["setup_hold_closure"] = {
    "id": "setup_hold_closure",
    "concern": "Setup / Hold 真正闭合 (全 corner)",
    "why": "单 corner 或单看 WNS 会漏 hold/多 corner 收敛问题",
    "inputs": ["STA reports (all corners)", "SDC", "library timing models (all PVT corners)"],
    "outputs": ["setup WNS/TNS/violations per corner", "hold WNS/TNS/violations per corner"],
    "decision": "Check ALL corners: setup WNS >= 0, hold WNS >= 0, violations == 0 "
                "across best/worst/typical PVT corners simultaneously. "
                "A single corner pass is NOT sign-off. Multi-corner multi-mode (MCMM) required.",
    "tool_commands": [
        "# PrimeTime MCMM",
        "pt_shell>",
        "  # Define modes/corners",
        "  set_operating_conditions -analysis_type on_chip_variation \\",
        "    -max ss_0p72v_m40c \\  # worst setup",
        "    -min ff_0p88v_125c      # worst hold",
        "  report_timing -delay_type max  # setup",
        "  report_timing -delay_type min  # hold",
        "  report_constraint -all_violators",
        "",
        "# Extract from report:",
        "  grep 'slack' timing_report.rpt | sort -n | head -20",
        "  grep 'VIOLATED' timing_report.rpt | wc -l",
    ],
    "report_interpretation": [
        "WNS (Worst Negative Slack): setup WNS >= 0 means all paths meet setup",
        "TNS (Total Negative Slack): TNS == 0 means no cumulative timing debt",
        "violations count: number of endpoints with negative slack, must be 0",
        "setup vs hold: BOTH must be clean simultaneously — fixing one can break the other",
        "Cross-corner: check all corners; ss corner for setup, ff corner for hold",
    ],
    "root_cause_patterns": [
        "Setup violation on reg-to-reg → logic too deep, needs pipelining or optimization",
        "Hold violation on reg-to-reg → buffer delay missing, needs hold fix cells",
        "Setup violation on I/O → missing set_input_delay or path too long from port",
        "Hold violation on I/O → missing set_output_delay or fast path from port",
        "Violation only in one corner → PVT-specific, check library timing",
        "Cross-domain violation → check if clock group is set correctly (or should be)",
    ],
    "pitfalls": [
        "Only checking setup → hold violations missed",
        "Only checking one corner → PVT-specific violations missed",
        "Using set_false_path to hide real timing paths → wrong",
        "Not checking recovery/removal on async reset → reset timing not verified",
        "Ignoring max_delay/min_delay on combinational paths",
    ],
    "handoff": {
        "gate": "setup_wns_ns >= 0 AND hold_wns_ps >= 0 AND violations == 0 (all corners)",
        "next_stage": "reset_cdc_lp_xprop",
        "if_fail": "Run physical optimization (ICC2 ECO), re-extract parasitics, re-run STA",
    },
    "rag_queries": {
        "manual": "setup hold timing closure slack PrimeTime corner",
        "dvcon_tag": "timing",
        "dvcon_query": "setup hold timing closure multi-corner",
    },
    "next_tools": [
        "chip_analyze_eda_log(kind=sta)",
        "chip_qor_trends(design=*, domain=sta)",
        "chip_rag_search(query='setup hold timing closure slack', backends=['manual_search'])",
    ],
}

STAGES["reset_cdc_lp_xprop"] = {
    "id": "reset_cdc_lp_xprop",
    "concern": "Reset / CDC / 低功耗 / X 传播引入的新问题",
    "why": "跨时钟/电源域与复位序列的 bug 只在结构级检查和专用仿真中出现",
    "inputs": ["RTL", "post-synthesis netlist", "UPF", "clock definition", "reset specification"],
    "outputs": ["CDC violation count (unwaived)", "UPF error count", "low-power assertion failures",
                "X-propagation count", "reset regression results"],
    "decision": "Run structural CDC analysis (SpyGlass/0-In) after synthesis. "
                "Run UPF simulation with power-aware semantics. "
                "Run X-propagation analysis (VCS X-prop). "
                "All unwaived violations must be 0 for sign-off.",
    "tool_commands": [
        "# SpyGlass CDC",
        "spyglass -project cdc.prj -goal cdc_unknown",
        "",
        "# VCS low-power simulation (UPF)",
        "vcs -full64 -kdb -debug_access+all \\",
        "    -power top_module_upf.tcl \\",
        "    +lp_insert_isolation +lp_insert_retention \\",
        "    +lp_pst_construct \\",
        "    tb_top.v",
        "",
        "# VCS X-propagation",
        "vcs -xprop=tmerge \\  # or xmerge for more aggressive",
        "    +xprop_assert +xprop_verbose",
    ],
    "report_interpretation": [
        "CDC report: 'synchronizer missing' = unsafe cross-domain path",
        "CDC report: 'reconvergence' = synchronizer outputs recombine unsafely",
        "UPF report: 'isolation missing' = signal crosses power domain without isolation",
        "UPF report: 'retention missing' = register loses state during power-down",
        "X-prop report: 'X source' → 'X destination' shows X propagation path",
        "Reset check: async assertion / sync de-assertion pattern",
    ],
    "root_cause_patterns": [
        "CDC: missing 2-flop synchronizer → add synchronizer or waive with justification",
        "CDC: reconvergent synchronizer → use handshake or async FIFO",
        "UPF: isolation missing → add isolation cell in UPF for domain crossing",
        "UPF: retention missing → add retention strategy for critical registers",
        "X-prop: uninitialized register → add reset or initialize in testbench",
        "Reset: async de-assertion → add reset synchronizer",
    ],
    "pitfalls": [
        "Waiving CDC violations without proper justification → functional bug escapes",
        "Running UPF simulation without proper power intent → misses isolation/retention bugs",
        "Not running X-prop → X-source bugs only found in silicon",
        "Ignoring reset synchronizer on async reset → metastability on de-assertion",
        "Assuming RTL sim covers CDC → RTL has no timing, CDC bugs invisible",
    ],
    "handoff": {
        "gate": "cdc_violations_unwaived == 0 AND upf_errors == 0 AND "
                "low_power_assertion_failures == 0 AND xprop_issues == 0 AND "
                "reset_regression_failures == 0",
        "next_stage": "eco_equivalence",
        "if_fail": "Fix RTL/UPF/SDC, re-synthesize, re-run all structural checks",
    },
    "rag_queries": {
        "manual": "CDC clock domain crossing UPF power intent X-propagation reset synchronizer",
        "dvcon_tag": "cdc",
        "dvcon_query": "CDC clock domain crossing verification",
    },
    "next_tools": [
        "chip_rag_search(query='CDC UPF X-propagation reset', backends=['manual_search','dvcon_index'])",
        "chip_run_simulation(extra_args=['-power','upf.tcl','-xprop=tmerge'])",
        "chip_analyze_eda_log(kind=vcs)",
    ],
}

STAGES["eco_equivalence"] = {
    "id": "eco_equivalence",
    "concern": "ECO 后功能等价性",
    "why": "每次 ECO 都可能引入新 bug, 必须在时序/物理修复后重新验证功能等价",
    "inputs": ["pre-ECO netlist (golden)", "post-ECO netlist (revised)", "ECO change list"],
    "outputs": ["ECO equivalence PASS/FAIL", "changed point list", "timing impact of ECO"],
    "decision": "After EVERY timing/physical ECO iteration, run LEC between pre-ECO and post-ECO netlists. "
                "If ECO changes logic (not just buffers/inverters), full sequential LEC required. "
                "If LEC fails, the ECO broke functionality — revert and re-plan ECO.",
    "tool_commands": [
        "# Formality post-ECO LEC",
        "fm_shell>",
        "  set_app_var synopsys_auto_setup true",
        "  read_verilog -r pre_eco_netlist.v",
        "  set_top r:/WORK/top_module",
        "  read_verilog -i post_eco_netlist.v",
        "  set_top i:/WORK/top_module",
        "  match",
        "  verify",
        "",
        "# If ECO is physical-only (buffer/inverter), quick check:",
        "  # Compare point counts and cell counts (excluding buffers)",
    ],
    "report_interpretation": [
        "Equivalence PASS → ECO is safe, proceed to re-run STA",
        "Equivalence FAIL → ECO changed logic unintentionally, revert",
        "Changed points: verify the list matches the intended ECO changes",
        "Unmatched after ECO → ECO tool renamed cells, update matching hints",
    ],
    "root_cause_patterns": [
        "ECO introduced new logic path → check ECO script for unintended changes",
        "ECO changed DFF → check if hold-fix cell replaced functional flop",
        "ECO restructured logic → synthesis tool optimization changed topology",
    ],
    "pitfalls": [
        "Skipping LEC after ECO → functionality silently broken",
        "Only running combinational LEC → sequential state mismatch missed",
        "Not comparing against the ORIGINAL pre-ECO golden reference",
        "Assuming buffer/inverter insertion is always functionally safe",
    ],
    "handoff": {
        "gate": "eco_equivalence_pass == true",
        "next_stage": "ppa_regression_guard",
        "if_fail": "Revert ECO, debug ECO script, re-plan timing fix",
    },
    "rag_queries": {
        "manual": "ECO equivalence checking Formality netlist",
        "dvcon_tag": "signoff",
        "dvcon_query": "ECO equivalence checking automated validation",
    },
    "next_tools": [
        "chip_design_pipeline(op=re_verify)",
        "chip_rag_search(query='ECO equivalence checking', backends=['manual_search','dvcon_index'])",
    ],
}

STAGES["ppa_regression_guard"] = {
    "id": "ppa_regression_guard",
    "concern": "PPA 优化后回归保护",
    "why": "任何 PPA 优化 (timing fix, area reduction, power optimization) 都可能破坏已有正确行为",
    "inputs": ["post-optimization netlist", "regression suite (baseline)", "PPA reports (before/after)"],
    "outputs": ["regression PASS/FAIL", "baseline diff", "PPA delta report (timing/power/area)"],
    "decision": "After ANY optimization step, re-run the FULL regression suite. "
                "Compare QoR (timing/power/area) against baseline. "
                "If regression fails or QoR degrades beyond threshold, revert optimization.",
    "tool_commands": [
        "# Regression re-run",
        "make regression SUITE=all",
        "# Compare against baseline",
        "diff regression_results/ regression_baseline/ > ppa_regress.diff",
        "",
        "# QoR comparison",
        "pt_shell> report_timing > after_opt_timing.rpt",
        "diff before_opt_timing.rpt after_opt_timing.rpt",
        "",
        "# Area/power",
        "report_area > after_area.rpt",
        "report_power > after_power.rpt",
    ],
    "report_interpretation": [
        "Regression: all tests must PASS (no new failures vs baseline)",
        "Timing: WNS/TNS must not degrade beyond threshold (e.g., -0.01ns)",
        "Power: static/dynamic power within sign-off budget",
        "Area: total cell area within sign-off budget",
        "QoR trends: chip_qor_trends detects cross-run drift",
    ],
    "root_cause_patterns": [
        "New regression failure after optimization → optimization broke functionality",
        "Timing degradation → optimization tool traded timing for power/area",
        "Power increase → optimization tool added unnecessary cells",
        "Area increase → optimization tool duplicated logic",
    ],
    "pitfalls": [
        "Running only a subset of regression → misses corner-case breakage",
        "Not comparing PPA against a frozen baseline → gradual drift goes unnoticed",
        "Skipping regression after 'harmless' optimization → false economy",
        "Not using QoR trend tracking → cumulative degradation invisible",
    ],
    "handoff": {
        "gate": "regression_failures == 0 AND baseline_regression_failures == 0 AND "
                "WNS >= 0 AND power <= budget AND area <= budget",
        "next_stage": "SIGN-OFF COMPLETE",
        "if_fail": "Revert optimization, investigate root cause, re-plan",
    },
    "rag_queries": {
        "manual": "PPA optimization regression baseline timing power area",
        "dvcon_tag": "signoff",
        "dvcon_query": "PPA optimization regression protection",
    },
    "next_tools": [
        "chip_qor_trends(design=*, domain=pd)",
        "chip_design_pipeline(op=status)",
        "chip_rag_search(query='PPA regression protection', backends=['dvcon_index'])",
    ],
}

# ---------------------------------------------------------------------------
# Stage dependency graph & ordering
# ---------------------------------------------------------------------------
STAGE_ORDER = list(STAGES.keys())  # ["lec", "gl_post_route_functional", ...]

STAGE_DEPENDENCIES = {
    "lec": [],
    "gl_post_route_functional": ["lec"],
    "sdc_clock_constraints": [],
    "setup_hold_closure": ["sdc_clock_constraints"],
    "reset_cdc_lp_xprop": ["gl_post_route_functional"],
    "eco_equivalence": ["setup_hold_closure"],  # ECO after timing analysis
    "ppa_regression_guard": ["eco_equivalence", "reset_cdc_lp_xprop"],
}

# Two parallel tracks that merge at PPA-guard:
#   Track A (functional): LEC → GL-sim → reset/CDC/LP/X-prop
#   Track B (physical):   SDC → STA → ECO
# Both merge at: PPA regression guard
TRACK_A = ["lec", "gl_post_route_functional", "reset_cdc_lp_xprop"]
TRACK_B = ["sdc_clock_constraints", "setup_hold_closure", "eco_equivalence"]
MERGE = ["ppa_regression_guard"]

# ---------------------------------------------------------------------------
# Multi-dimensional convergence tracking
# ---------------------------------------------------------------------------
CONVERGENCE_DIMENSIONS = OrderedDict([
    ("function", ["lec_pass", "gl_functional_pass", "regression_pass"]),
    ("timing", ["sdc_clean", "setup_wns >= 0", "hold_wns >= 0", "violations == 0"]),
    ("power", ["upf_errors == 0", "static_power <= budget", "dynamic_power <= budget"]),
    ("area", ["area <= budget", "cell_count <= budget"]),
    ("physical", ["drc_clean", "lvs_clean", "antenna_clean"]),
])

# ---------------------------------------------------------------------------
# Intent routing: query → stage(s)
# ---------------------------------------------------------------------------
_STAGE_KEYWORDS = [
    (["lec", "equivalence", "formality", "conformal", "等价", "综合后"], ["lec"]),
    (["gate level", "gl_sim", "netlist", "post-route", "sdf", "门级"], ["gl_post_route_functional"]),
    (["sdc", "clock constraint", "check_timing", "unconstrained", "约束"], ["sdc_clock_constraints"]),
    (["setup", "hold", "wns", "tns", "timing closure", "slack", "violat"], ["setup_hold_closure"]),
    (["cdc", "reset", "x-prop", "xprop", "upf", "low power", "isolation",
      "retention", "cross domain", "复位", "低功耗"], ["reset_cdc_lp_xprop"]),
    (["eco", "engineering change order", "post-eco", "eco equivalence", "eco timing fix"], ["eco_equivalence"]),
    (["ppa", "regression", "baseline", "optimization", "qor", "回归"], ["ppa_regression_guard"]),
    (["signoff", "tapeout", "full flow", "全流程", "签核"],
     list(STAGES.keys())),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_stage(stage_key: str) -> dict:
    if stage_key not in STAGES:
        return {"error": f"unknown stage: {stage_key}",
                "available": list(STAGES.keys())}
    s = dict(STAGES[stage_key])
    s["stage_key"] = stage_key
    s["depends_on"] = STAGE_DEPENDENCIES.get(stage_key, [])
    s["rag_queries"] = s.get("rag_queries", {})
    return s


def list_stages() -> list[str]:
    return list(STAGES.keys())


def decide(query: str) -> dict:
    """Route a query to the most relevant post-RTL stage(s)."""
    q = query.lower()
    matches = []
    for keywords, stages in _STAGE_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in q)
        if hits > 0:
            matches.append({"score": hits, "stages": stages})
    if not matches:
        return {
            "query": query, "matched": False,
            "available_stages": list(STAGES.keys()),
            "message": "No post-RTL stage matched. Try keywords like: LEC, gate-level, "
                       "SDC, setup, hold, CDC, UPF, ECO, PPA, regression, signoff",
        }
    matches.sort(key=lambda x: -x["score"])
    best = matches[0]
    result = {"query": query, "matched": True,
              "best_stages": best["stages"], "score": best["score"]}
    if len(best["stages"]) == 1:
        key = best["stages"][0]
        result["stage_data"] = get_stage(key)
    else:
        result["stage_data"] = {k: get_stage(k) for k in best["stages"]}
    result["alternatives"] = [
        {"stages": m["stages"], "score": m["score"]} for m in matches[1:3]
    ]
    return result


def get_full_workflow() -> dict:
    """End-to-end orchestration plan for all 7 stages."""
    return {
        "tracks": {
            "track_a_functional": TRACK_A,
            "track_b_physical": TRACK_B,
            "merge": MERGE,
        },
        "stage_order": STAGE_ORDER,
        "dependencies": STAGE_DEPENDENCIES,
        "convergence_dimensions": {
            k: v for k, v in CONVERGENCE_DIMENSIONS.items()
        },
        "stages": {k: get_stage(k) for k in STAGE_ORDER},
    }


def convergence_status(measurements: dict) -> dict:
    """Given measured values, assess multi-dimensional convergence readiness."""
    # measurements format: {"setup_wns_ns": -0.05, "hold_wns_ps": 15, ...}
    checks = []
    # Function
    checks.append({"dim": "function", "check": "lec_pass",
                   "ok": measurements.get("lec_pass", False)})
    checks.append({"dim": "function", "check": "gl_functional_pass",
                   "ok": measurements.get("gl_functional_failures", 1) == 0})
    # Timing
    checks.append({"dim": "timing", "check": "setup_wns",
                   "ok": measurements.get("setup_wns_ns", -1) >= 0})
    checks.append({"dim": "timing", "check": "hold_wns",
                   "ok": measurements.get("hold_wns_ps", -1) >= 0})
    # Power
    checks.append({"dim": "power", "check": "upf_errors",
                   "ok": measurements.get("upf_errors", 1) == 0})
    # Area
    checks.append({"dim": "area", "check": "area_budget",
                   "ok": measurements.get("area_within_budget", False)})
    # Physical
    checks.append({"dim": "physical", "check": "drc_clean",
                   "ok": measurements.get("drc_violations", 1) == 0})

    dims_ok = {}
    for c in checks:
        dims_ok.setdefault(c["dim"], []).append(c["ok"])

    return {
        "checks": checks,
        "all_pass": all(c["ok"] for c in checks),
        "by_dimension": {k: {"all_ok": all(v), "items": len(v), "passed": sum(v)}
                        for k, v in dims_ok.items()},
        "failing": [c for c in checks if not c["ok"]],
    }


def get_pitfalls(stage_key: str | None = None) -> list[dict]:
    if stage_key:
        if stage_key not in STAGES:
            return []
        return [{"stage": stage_key, "pitfall": p}
                for p in STAGES[stage_key].get("pitfalls", [])]
    out = []
    for key, stage in STAGES.items():
        for p in stage.get("pitfalls", []):
            out.append({"stage": key, "pitfall": p})
    return out


def get_tool_chain(stage_key: str) -> list[str]:
    if stage_key in STAGES:
        return STAGES[stage_key].get("next_tools", [])
    return []


def post_rtl_checklist_for_intent(query: str) -> dict:
    """Given an intent, return matching stage(s) + convergence checklist."""
    decision = decide(query)
    if not decision.get("matched"):
        return decision
    stages = decision.get("best_stages", [])
    checklist = []
    for s in stages:
        st = STAGES.get(s, {})
        checklist.append({
            "stage": s,
            "id": st.get("id", s),
            "concern": st.get("concern", ""),
            "handoff_gate": st.get("handoff", {}).get("gate", ""),
            "if_fail": st.get("handoff", {}).get("if_fail", ""),
            "next_tools": st.get("next_tools", []),
            "rag_queries": st.get("rag_queries", {}),
        })
    return {
        "query": query, "matched": True,
        "best_stages": stages,
        "checklist": checklist,
        "full_workflow_available": True,
    }
