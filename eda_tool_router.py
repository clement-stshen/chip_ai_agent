"""EDA tool routing validation: maps intent → recipe → tool → command template.

Ensures the agent dispatches the correct EDA tool for each task:
  - compile/simv       → VCS      (vcs binary, -full64 -sverilog, ./simv)
  - dump/view fsdb     → Verdi    (verdi binary, -ssf <file>)
  - CDC/lint/structural → SpyGlass (spyglass binary, -project, -goal)
  - SDC/constraint     → PrimeTime (pt_shell, read_sdc, check_timing)
  - formal/LEC         → Formality/VC Formal (fm_shell, read_sverilog, verify)
  - synthesis          → Design Compiler (dc_shell, compile_ultra)
  - PD/place-route     → ICC2 (icc2_shell, place_opt, route_opt)
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tool-to-intent mapping
# ---------------------------------------------------------------------------

@dataclass
class ToolRoute:
    """A single EDA tool route: what intent maps to which tool and command."""
    intent_keywords: list[str]
    recipe: str
    tool_name: str
    domain: str
    binary: str
    command_template: list[str]
    run_command: list[str]
    validation_flags: list[str]
    output_files: list[str]
    log_files: list[str]
    availability_check: str  # env var or binary name
    common_args: dict = field(default_factory=dict)
    pitfalls: list[str] = field(default_factory=list)


TOOL_ROUTES = OrderedDict()

TOOL_ROUTES["vcs_compile_sim"] = ToolRoute(
    intent_keywords=["compile", "vcs", "simv", "simulate", "simulation",
                     "run simulation", "elaborate", "仿真", "编译",
                     "run_vcs", "gate-level sim", "gl sim"],
    recipe="simulation_run",
    tool_name="VCS",
    domain="verification",
    binary="vcs",
    command_template=[
        "vcs", "-full64", "-sverilog", "-timescale=1ns/1ps",
        "-debug_access+all", "+incdir+{uvm_home}/src",
        "-f", "{filelist}", "-l", "comp.log", "-o", "simv",
    ],
    run_command=["./simv", "+UVM_TESTNAME={testname}",
                 "+UVM_VERBOSITY=UVM_LOW", "-l", "sim.log"],
    validation_flags=["-full64", "-sverilog", "-debug_access+all", "-o simv"],
    output_files=["simv"],
    log_files=["comp.log", "sim.log"],
    availability_check="VCS_HOME",
    common_args={
        "coverage": ["-cm", "line+cond+fsm+tgl+branch+assert"],
        "low_power": ["-power", "upf.tcl", "+lp_insert_isolation"],
        "xprop": ["-xprop=tmerge", "+xprop_assert"],
        "sdf": ["-sdf", "max:top:top.sdf", "+neg_tchk"],
        "sverilog": ["-sverilog"],
        "debug": ["-debug_access+all", "-kdb"],
    },
    pitfalls=[
        "Missing -full64 on 64-bit Linux → 32-bit mode → library mismatch",
        "Forgetting -sverilog → SystemVerilog constructs rejected",
        "Missing -debug_access+all → no FSDB dumping possible",
        "Wrong +incdir+ path → uvm_macros.svh not found",
        "No -l comp.log → compilation errors invisible to agent",
    ],
)

TOOL_ROUTES["verdi_waveform"] = ToolRoute(
    intent_keywords=["fsdb", "verdi", "waveform", "dump", "wave",
                     "view waveform", "看波形", "波形", "debug waveform",
                     "signal trace", "nwave", "verdi debug"],
    recipe="waveform_forensics",
    tool_name="Verdi",
    domain="verification",
    binary="verdi",
    command_template=[
        "verdi", "-nologo", "-ssf", "{fsdb_file}",
    ],
    run_command=[],  # Verdi is interactive, run command = command_template
    validation_flags=["-nologo", "-ssf"],
    output_files=["verdi.log"],
    log_files=["verdi.log"],
    availability_check="VERDI_HOME",
    common_args={
        "with_signals": ["-s", "{signal}"],
        "batch_mode": ["-batch"],
        "session": ["-play", "{session_file}"],
        "compare": ["-ssf", "{ref_fsdb}", "-ssf2", "{test_fsdb}"],
    },
    pitfalls=[
        "Missing -nologo → GUI launch blocks agent (non-interactive)",
        "Wrong -ssf path → 'file not found' error",
        "Forgetting -batch for automated analysis → hangs",
        "FSDB not generated during simulation → need -debug_access+all in VCS",
    ],
)

TOOL_ROUTES["spyglass_cdc_lint"] = ToolRoute(
    intent_keywords=["spyglass", "cdc", "lint", "cdc lint", "structural",
                     "crossing", "rtl check", "cdc check", "lint check",
                     "clock domain", "reset domain", "rdc"],
    recipe="rtl_design_flow",
    tool_name="SpyGlass",
    domain="rtl-design",
    binary="spyglass",
    command_template=[
        "spyglass", "-project", "{project}.prj",
        "-goal", "{goal}",  # e.g. cdc_unknown, lint_rtl, sdc_lint
        "-batch",
    ],
    run_command=[],  # batch mode, no separate run
    validation_flags=["-project", "-goal", "-batch"],
    output_files=["{project}/spyglass_report/"],
    log_files=["spyglass.log"],
    availability_check="SPYGLASS_HOME",
    common_args={
        "cdc": ["-goal", "cdc_unknown"],
        "lint": ["-goal", "lint_rtl"],
        "sdc_lint": ["-goal", "sdc_lint"],
        "reset_domain": ["-goal", "reset_domain_crossing"],
    },
    pitfalls=[
        "Missing -batch in automated flow → GUI launch blocks agent",
        "Wrong -goal name → silently runs wrong analysis",
        "Not reviewing waivers → real violations hidden",
        "Running CDC on RTL only (not post-synthesis) → misses gate-level crossings",
    ],
)

TOOL_ROUTES["primetime_sta_sdc"] = ToolRoute(
    intent_keywords=["sdc", "primetime", "timing", "setup", "hold",
                     "wns", "tns", "slack", "check_timing",
                     "constraint", "timing report", "sta", "violation"],
    recipe="sta_timing_flow",
    tool_name="PrimeTime",
    domain="sta",
    binary="pt_shell",
    command_template=[
        "pt_shell", "-f", "{script}.tcl",
    ],
    run_command=[],
    validation_flags=["read_sdc", "check_timing", "report_timing"],
    output_files=["timing_report.rpt"],
    log_files=["pt_shell.log"],
    availability_check="PRIMETIME_HOME",
    common_args={
        "read_sdc": ["read_sdc", "{sdc_file}"],
        "check_timing": ["check_timing", "-verbose"],
        "report_timing": ["report_timing", "-delay_type", "max"],
        "report_hold": ["report_timing", "-delay_type", "min"],
        "all_violators": ["report_constraint", "-all_violators"],
    },
    pitfalls=[
        "Interpreting WNS without check_timing → false convergence",
        "Only checking setup (max) → hold violations missed",
        "Only checking one corner → PVT-specific violations missed",
        "Missing link_design before report_timing → no data",
    ],
)

TOOL_ROUTES["formality_lec"] = ToolRoute(
    intent_keywords=["lec", "formality", "equivalence", "conformal",
                     "formal equivalence", "post-synthesis", "sequential"],
    recipe="formal_verification_flow",
    tool_name="Formality",
    domain="formal",
    binary="fm_shell",
    command_template=[
        "fm_shell", "-f", "{script}.tcl",
    ],
    run_command=[],
    validation_flags=["read_sverilog", "read_verilog", "match", "verify"],
    output_files=["fm_report.txt"],
    log_files=["fm_shell.log"],
    availability_check="FORMALITY_HOME",
    common_args={
        "read_rtl": ["read_sverilog", "-r", "{rtl_files}"],
        "read_netlist": ["read_verilog", "-i", "{netlist}"],
        "set_top": ["set_top", "r:/WORK/{module}"],
        "match": ["match"],
        "verify": ["verify"],
    },
    pitfalls=[
        "Not setting synopsys_auto_setup true → SDC mismatch false failures",
        "Forgetting black boxes for memories → unmatched points",
        "Running only top module LEC → sub-module mismatches missed",
    ],
)

TOOL_ROUTES["dc_synthesis"] = ToolRoute(
    intent_keywords=["synthesis", "dc_shell", "design compiler", "compile_ultra",
                     "map", "gate-level netlist", "逻辑综合"],
    recipe="logic_synthesis_flow",
    tool_name="Design Compiler",
    domain="synthesis",
    binary="dc_shell",
    command_template=[
        "dc_shell", "-f", "{script}.tcl",
    ],
    run_command=[],
    validation_flags=["read_verilog", "compile_ultra", "write_verilog"],
    output_files=["netlist.v", "ddc_file.ddc", "sdc_file.sdc"],
    log_files=["dc_shell.log"],
    availability_check="DC_HOME",
    common_args={
        "compile": ["compile_ultra", "-scan"],
        "read_lib": ["set_target_library", "{lib}.db"],
        "write_netlist": ["write_verilog", "-hierarchy", "netlist.v"],
        "write_sdc": ["write_sdc", "output.sdc"],
    },
    pitfalls=[
        "Missing set_dont_touch on clock gating → LEC unmatched",
        "Not writing SDC → STA has no constraints",
        "Wrong library corner → timing not representative",
    ],
)

TOOL_ROUTES["icc2_place_route"] = ToolRoute(
    intent_keywords=["icc2", "place", "route", "cts", "floorplan",
                     "physical design", "post-route", "place and route",
                     "布线", "布局"],
    recipe="physical_design_flow",
    tool_name="ICC2",
    domain="pd",
    binary="icc2_shell",
    command_template=[
        "icc2_shell", "-f", "{script}.tcl",
    ],
    run_command=[],
    validation_flags=["create_block", "place_opt", "clock_opt", "route_opt"],
    output_files=["design.nlib", "routed_netlist.v", "parasitics.spef"],
    log_files=["icc2_shell.log"],
    availability_check="ICC2_HOME",
    common_args={
        "floorplan": ["initialize_floorplan"],
        "place": ["place_opt"],
        "cts": ["clock_opt"],
        "route": ["route_opt"],
    },
    pitfalls=[
        "Skipping clock_opt → clock tree not built → timing meaningless",
        "Not writing SPEF → STA parasitics missing",
        "Not running route_opt → DRC violations",
    ],
)

TOOL_ROUTES["conformal_lec"] = ToolRoute(
    intent_keywords=["conformal", "cadence lec", "cadence equivalence",
                     "conformal lec", "conformal equivalence",
                     "cadence formal", "low power lec",
                     "conformal low power", "lec alternative"],
    recipe="formal_verification_flow",
    tool_name="Conformal",
    domain="formal",
    binary="lec",
    command_template=[
        "lec", "-nogui",
        "-dofile", "{script}.do",
    ],
    run_command=[],
    validation_flags=["read_design", "compare", "report"],
    output_files=["lec_report.txt", "lec_log"],
    log_files=["lec.log"],
    availability_check="CONFORMAL_HOME",
    common_args={
        "read_rtl": ["read_design", "-golden", "-sverilog", "{rtl_files}"],
        "read_netlist": ["read_design", "-revised", "-verilog", "{netlist}"],
        "set_options": ["set_system_mode", "lec"],
        "compare": ["compare", "-sequential"],
        "report": ["report", "-compare", "verify"],
    },
    pitfalls=[
        "Missing -nogui in batch mode → GUI launch blocks agent",
        "Wrong -golden/-reversed mapping → false comparison",
        "Not specifying comparison mode (combinational vs sequential) → wrong equivalence check",
        "Missing library path for gate-level LEC → unmapped cells",
        "Forgetting add_timescale for RTL → timing mismatch with netlist",
    ],
)

TOOL_ROUTES["jaspergold_fpv"] = ToolRoute(
    intent_keywords=["jaspergold", "jasper", "ddi", "cadence fpv",
                     "formal property", "fpv", "jaspergold fpv",
                     "cadence proof", "assertion proof", "proof assistant",
                     "bounded model check", "induction"],
    recipe="formal_verification_flow",
    tool_name="JasperGold",
    domain="formal",
    binary="jasper",
    command_template=[
        "jasper", "-proj", "{project}.jasp",
        "-cmd", "{script}.tcl",
        "-batch",
    ],
    run_command=[],
    validation_flags=["-proj", "-cmd", "-batch", "proof"],
    output_files=["jasper_report.txt", "proof_status.xml"],
    log_files=["jasper.log"],
    availability_check="JASPER_HOME",
    common_args={
        "run_proof": ["proof", "-property", "{assertion}"],
        "bounded": ["prove", "-bounded", "-depth", "20"],
        "induction": ["prove", "-induction"],
        "cover": ["cover", "-property", "{cover_property}"],
        "elaborate": ["elaborate", "-top", "{top_module}"],
    },
    pitfalls=[
        "Missing -batch in automated flow → GUI launch blocks agent",
        "Overly broad assertion set → proof timeout (use bounded first)",
        "Missing SVA library import → assertion syntax errors",
        "Wrong -top module → proof target not found",
        "Not using incremental proof → re-proving all properties each run",
    ],
)

TOOL_ROUTES["calibre_drc_lvs"] = ToolRoute(
    intent_keywords=["calibre", "drc", "lvs", "drc/lvs", "physical verify",
                     "physical verification", "antenna", "design rule",
                     "layout vs schematic", "siemens", "mentor",
                     "physical check", "calibre drc", "calibre lvs",
                     "drc clean", "lvs clean", "physical signoff",
                     "规则检查", "物理验证", "版图检查"],
    recipe="signoff_tapeout",
    tool_name="Calibre",
    domain="pd",
    binary="calibre",
    command_template=[
        "calibre", "-drc" , "{rule_deck}.drc",
        "{layout}.gds",
        "-hier", "{svdb_file}",
    ],
    run_command=[],
    validation_flags=["calibre", "-drc", "-hier"],
    output_files=["calibre_results.db", "drc_report", "lvs_report"],
    log_files=["calibre.log"],
    availability_check="CALIBRE_HOME",
    common_args={
        "drc": ["calibre", "-drc", "{rule_deck}.drc", "{layout}.gds"],
        "lvs": ["calibre", "-lvs", "{rule_deck}.lvs", "{layout}.gds", "{source_netlist}"],
        "antenna": ["calibre", "-drc", "-antenna", "{rule_deck}.drc", "{layout}.gds"],
        "xrc": ["calibre", "-xrc", "{rule_deck}.xrc", "{layout}.gds"],
        "batch": ["calibre", "-batch", "{script}.tcl"],
    },
    pitfalls=[
        "Wrong GDS layer mapping → false DRC violations",
        "Missing SVDB database → LVS hierarchical comparison fails",
        "Not running antenna check → silicon reliability risk",
        "Wrong rule deck version → missing new rules or false violations",
        "Skipping LVS after ECO → netlist/layout mismatch escapes",
        "Not checking density rules → CMP/etch issues in fab",
        "Forgetting to include fill patterns in DRC → density violations missed",
    ],
)

TOOL_ROUTES["questa_sim"] = ToolRoute(
    intent_keywords=["questa", "questa sim", "vsim", "mentor simulation",
                     "siemens simulation", "questa simulate"],
    recipe="simulation_run",
    tool_name="Questa",
    domain="verification",
    binary="vsim",
    command_template=[
        "vlib", "{work_lib}",
        "vlog", "-sv", "+incdir+{uvm_home}/src", "-f", "{filelist}",
        "vsim", "-c", "-do", "{run_script}.do", "+UVM_TESTNAME={testname}",
    ],
    run_command=[],
    validation_flags=["vlib", "vlog", "vsim"],
    output_files=["work/", "vsim.wlf"],
    log_files=["vsim.log"],
    availability_check="QUESTA_HOME",
    common_args={
        "compile": ["vlog", "-sv", "+incdir+{uvm_home}/src"],
        "coverage": ["vlog", "+cover=sbtef+"],
        "gui": ["vsim", "-gui"],
        "batch": ["vsim", "-c", "-do", "run -all; quit"],
    },
    pitfalls=[
        "Missing vlib before vlog → work library not created",
        "Wrong -sv flag → SystemVerilog constructs rejected",
        "Forgetting -c for batch mode → GUI hangs agent",
        "Missing +incdir+ for UVM → compilation errors",
    ],
)

TOOL_ROUTES["innovus_place_route"] = ToolRoute(
    intent_keywords=["innovus", "cadence place", "cadence route",
                     "cadence pd", "cadence physical design",
                     "innovus place", "innovus route", "cadence cts"],
    recipe="physical_design_flow",
    tool_name="Innovus",
    domain="pd",
    binary="innovus",
    command_template=[
        "innovus", "-no_gui", "-files", "{script}.tcl",
    ],
    run_command=[],
    validation_flags=["innovus", "-no_gui", "-files"],
    output_files=["innovus.log", "routed_design.ddb"],
    log_files=["innovus.log"],
    availability_check="INNOVUS_HOME",
    common_args={
        "floorplan": ["place_design", "-timing_driven"],
        "cts": ["ccopt_design"],
        "route": ["route_design"],
        "report_timing": ["report_timing", "-delay_type", "max"],
    },
    pitfalls=[
        "Missing -no_gui → GUI blocks agent in batch mode",
        "Skipping ccopt_design → clock tree not built",
        "Not loading timing constraints before place → poor QoR",
    ],
)


# ---------------------------------------------------------------------------
# Intent → tool route matching
# ---------------------------------------------------------------------------
# ─── VCS X-Propagation ───
TOOL_ROUTES["vcs_xprop"] = ToolRoute(
    intent_keywords=["xprop", "x-prop", "x propagation", "x source", "x trace", "unknown state"],
    recipe="x_prop_debug", tool_name="VCS Xprop", domain="verification", binary="vcs",
    command_template=["vcs", "-sverilog", "-xprop=xprop_config_file", "-f", "{filelist}"],
    run_command=["./simv", "+UVM_TESTNAME={testname}"],
    validation_flags=["-xprop"], output_files=["simv"], log_files=["xprop.log"],
    availability_check="VCS_HOME",
    common_args={"tmerge": ["-xprop=tmerge"], "xmerge": ["-xprop=xmerge"],
                 "assert": ["+xprop_assert"], "verbose": ["+xprop_verbose"]},
    pitfalls=["xprop adds runtime overhead ~10-30%", "tmerge is less aggressive than xmerge",
              "Requires -debug_access+all for FSDB dumping"])

# ─── VCS ISR (Interactive Simulation Restart) ───
TOOL_ROUTES["vcs_isr"] = ToolRoute(
    intent_keywords=["isr", "interactive restart", "simulation restart", "isr restart", "isr checkpoint", "isr replay", "solver bias isr"],
    recipe="simulation_run", tool_name="VCS ISR", domain="verification", binary="vcs",
    command_template=["vcs", "-sverilog", "{source}.v", "-o", "simv1"],
    run_command=["./simv1", "+ntb_solver_bias_isr=1",
                 "+ntb_solver_bias_isr_record=isr_record", "-lca"],
    validation_flags=["+ntb_solver_bias_isr"],
    output_files=["isr_record/"], log_files=["simv_isr_record.log"],
    availability_check="VCS_HOME",
    common_args={"record": ["+ntb_solver_bias_isr=1", "+ntb_solver_bias_isr_record=isr_record"],
                 "replay": ["+ntb_solver_bias_isr_replay=isr_record"],
                 "cache": ["+ntb_solver_bias_isr_cache=1"],
                 "ico_record": ["+ntb_solver_bias_isr=1", "+ntb_solver_bias_isr_record=isr_record",
                                "+ntb_solver_bias_mode_auto=5"]},
    pitfalls=["ISR record must run before replay", "Replay uses cached solver results for speedup",
              "Cache mode further accelerates subsequent replays"])

# ─── VCS fastcomp ───
TOOL_ROUTES["vcs_fastcomp"] = ToolRoute(
    intent_keywords=["fastcomp", "fast compile", "fast elaboration", "il mop"],
    recipe="logic_synthesis_flow", tool_name="VCS fastcomp", domain="synthesis", binary="vcs",
    command_template=["vcs", "{top}", "-fastcomp=il,mop", "-lca"],
    run_command=["./simv"],
    validation_flags=["-fastcomp"], output_files=["simv"], log_files=["comp.log"],
    availability_check="VCS_HOME",
    common_args={"il_mop": ["-fastcomp=il,mop"], "il": ["-fastcomp=il"]},
    pitfalls=["fastcomp=il,mop improves elaboration time", "Requires -lca flag",
              "Only for VHDL/Mixed designs"])

# ─── VCS Error Message Control ───
TOOL_ROUTES["vcs_msg_ctrl"] = ToolRoute(
    intent_keywords=["msg_config", "error message control", "suppress warning",
                     "message filtering", "warn_config"],
    recipe="simulation_run", tool_name="VCS MsgCtrl", domain="verification", binary="vcs",
    command_template=["vcs", "{top}", "-debug_access+all", "-msg_config={config_file}", "-sverilog"],
    run_command=["./simv"],
    validation_flags=["-msg_config"], output_files=["simv"], log_files=["comp.log"],
    availability_check="VCS_HOME",
    common_args={"module_filter": ["-msg_config=warn_mod.config"]},
    pitfalls=["Config file specifies module-level message filtering"])

# ─── VCS save_restore ───
TOOL_ROUTES["vcs_save_restore"] = ToolRoute(
    intent_keywords=["save", "restore", "checkpoint", "simulation save", "restart"],
    recipe="simulation_run", tool_name="VCS Save/Restore", domain="verification", binary="vcs",
    command_template=["vcs", "{top}", "-debug_access+all", "-full64"],
    run_command=["./simv", "-save", "{checkpoint_file}"],
    validation_flags=["-save"], output_files=["{checkpoint_file}"],
    log_files=["save_restore.log"], availability_check="VCS_HOME",
    common_args={"save": ["-save", "checkpoint.dat"],
                 "restore": ["-restore", "checkpoint.dat"]},
    pitfalls=["Save/restore requires identical binary and library versions",
              "ASLR must be disabled for save/restore to work"])

# ─── VCS FGP (Fine-Grained Profiling) ───
TOOL_ROUTES["vcs_fgp"] = ToolRoute(
    intent_keywords=["fgp", "fine-grained profiling", "simprofile", "performance profiling",
                     "simulation profile", "cpu time analysis"],
    recipe="simulation_run", tool_name="VCS FGP", domain="verification", binary="vcs",
    command_template=["vcs", "{top}", "-simprofile", "-simprofile_time", "-full64"],
    run_command=["./simv"],
    validation_flags=["-simprofile"], output_files=["simprofile_dir/"],
    log_files=["simprofile.log"], availability_check="VCS_HOME",
    common_args={"time": ["-simprofile_time"], "dir": ["-simprofile_dir=simprofile_dir"]},
    pitfalls=["simprofile adds ~5-10% runtime overhead",
              "profrpt tool generates report from profile data"])

# ─── Verdi nECO ───
TOOL_ROUTES["verdi_neco"] = ToolRoute(
    intent_keywords=["neco", "netlist eco", "verdi eco", "schematic eco", "gate level eco"],
    recipe="physical_design_flow", tool_name="Verdi nECO", domain="pd", binary="verdi",
    command_template=["verdi", "-nologo", "-eco"],
    run_command=[], validation_flags=["-eco"], output_files=["eco_report"],
    log_files=["verdi_eco.log"], availability_check="VERDI_HOME",
    common_args={}, pitfalls=["nECO requires KDB database from VCS -kdb compile"])

# ─── Verdi FaultAnalysis ───
TOOL_ROUTES["verdi_fault"] = ToolRoute(
    intent_keywords=["fault analysis", "fault injection", "fault simulation",
                     "safety analysis", "iso 26262", "fault campaign"],
    recipe="signoff_tapeout", tool_name="Verdi FaultAnalysis", domain="pd", binary="verdi",
    command_template=["verdi", "-nologo", "-fault"],
    run_command=[], validation_flags=["-fault"], output_files=["fault_report"],
    log_files=["verdi_fault.log"], availability_check="VERDI_HOME",
    common_args={}, pitfalls=["Fault analysis requires safety goal and fault model configuration"])

# ─── Verdi IDX (Intelligent Debug Acceleration) ───
TOOL_ROUTES["verdi_idx"] = ToolRoute(
    intent_keywords=["idx", "intelligent debug", "debug acceleration", "ip debug",
                     "aip debug", "eip debug", "sva debug", "waveform replay"],
    recipe="uvm_verification_flow", tool_name="Verdi IDX", domain="verification", binary="verdi",
    command_template=["verdi", "-nologo", "-ssf", "{fsdb}"],
    run_command=[], validation_flags=[], output_files=["idx_report"],
    log_files=["verdi_idx.log"], availability_check="VERDI_HOME",
    common_args={"ip_debug": ["-idx", "ip_debug"],
                 "sva_debug": ["-idx", "sva_debug"],
                 "waveform_replay": ["-idx", "waveform_replay"]},
    pitfalls=["IDX requires -kdb compile for design database",
              "IDX IP Debug accelerates IP-level debugging by mapping compiler metadata"])


def match_tool_route(query: str) -> dict:
    """Match an intent to the best EDA tool route.
    
    Scoring: exact tool name match > specific keyword > generic keyword.
    This prevents "conformal LEC" from matching Formality (which also has "lec").
    """
    q = query.lower()
    matches = []
    for route_key, route in TOOL_ROUTES.items():
        # Score 1: exact tool name or binary name in query (highest priority)
        # Use word-boundary matching to prevent short binary names like "lec"
        # from matching any occurrence of "lec" in arbitrary text.
        import re as _re
        name_score = 0
        if _re.search(rf"\b{_re.escape(route.tool_name.lower())}\b", q):
            name_score = 10
        elif len(route.binary) > 3 and _re.search(rf"\b{_re.escape(route.binary.lower())}\b", q):
            name_score = 8
        elif route.binary.lower() == q.strip():  # exact match for short names
            name_score = 8
        # Score 2: vendor-specific compound keywords (medium priority)
        vendor_score = 0
        specific_kws = [kw for kw in route.intent_keywords
                        if len(kw.split()) > 1]  # multi-word = more specific
        vendor_score = sum(2 for kw in specific_kws if kw in q)
        # Score 3: generic single-word keywords (lowest priority)
        generic_kws = [kw for kw in route.intent_keywords
                       if len(kw.split()) <= 1]
        generic_score = sum(1 for kw in generic_kws if kw in q)
        
        total_score = name_score + vendor_score + generic_score
        if total_score > 0:
            matches.append({"route_key": route_key, "score": total_score, "route": route})
    
    if not matches:
        return {
            "query": query, "matched": False,
            "available_routes": list(TOOL_ROUTES.keys()),
            "message": "No EDA tool route matched. Try keywords like: compile, simv, "
                       "fsdb, verdi, cdc, spyglass, sdc, primetime, lec, formality",
        }
    matches.sort(key=lambda x: -x["score"])
    best = matches[0]
    route = best["route"]
    return {
        "query": query,
        "matched": True,
        "route_key": best["route_key"],
        "score": best["score"],
        "tool_name": route.tool_name,
        "domain": route.domain,
        "binary": route.binary,
        "command_template": route.command_template,
        "run_command": route.run_command,
        "validation_flags": route.validation_flags,
        "output_files": route.output_files,
        "log_files": route.log_files,
        "availability_check": route.availability_check,
        "common_args": route.common_args,
        "pitfalls": route.pitfalls,
        "alternatives": [{"route_key": m["route_key"], "tool": m["route"].tool_name}
                        for m in matches[1:3]],
    }


def validate_command(tool_key: str, command: list[str]) -> dict:
    """Validate a generated EDA command against the expected template."""
    if tool_key not in TOOL_ROUTES:
        return {"error": f"unknown tool: {tool_key}"}
    route = TOOL_ROUTES[tool_key]
    cmd_str = " ".join(command)
    checks = []
    for flag in route.validation_flags:
        # Handle flags with arguments
        if flag.endswith("+") or flag.startswith("+"):
            ok = flag in cmd_str
        elif " " in flag:
            parts = flag.split()
            ok = all(p in cmd_str for p in parts)
        else:
            ok = flag in cmd_str
        checks.append({"flag": flag, "ok": ok})

    binary_ok = route.binary in command[0] if command else False
    return {
        "tool": route.tool_name,
        "binary": route.binary,
        "binary_ok": binary_ok,
        "command": " ".join(command),
        "checks": checks,
        "all_ok": binary_ok and all(c["ok"] for c in checks),
    }


def check_availability(route_key: str) -> dict:
    """Check if the EDA tool is available on this system."""
    if route_key not in TOOL_ROUTES:
        return {"error": f"unknown route: {route_key}"}
    route = TOOL_ROUTES[route_key]
    import os
    import shutil
    env_var = route.availability_check
    env_val = os.environ.get(env_var, "")
    binary_found = shutil.which(route.binary) is not None
    return {
        "tool": route.tool_name,
        "binary": route.binary,
        "env_var": env_var,
        "env_value": env_val,
        "binary_on_path": binary_found,
        "available": binary_found or bool(env_val),
    }


def get_all_routes() -> list[dict]:
    """List all EDA tool routes."""
    return [
        {
            "key": key,
            "tool": r.tool_name,
            "domain": r.domain,
            "binary": r.binary,
            "intent_keywords": r.intent_keywords[:5],
            "recipe": r.recipe,
        }
        for key, r in TOOL_ROUTES.items()
    ]


def get_pitfalls(route_key: str | None = None) -> list[dict]:
    if route_key:
        if route_key not in TOOL_ROUTES:
            return []
        return [{"route": route_key, "pitfall": p} for p in TOOL_ROUTES[route_key].pitfalls]
    out = []
    for key, r in TOOL_ROUTES.items():
        for p in r.pitfalls:
            out.append({"route": key, "tool": r.tool_name, "pitfall": p})
    return out


# VCS DPO/ICO performance optimization routes
TOOL_ROUTES["vcs_dpo"] = ToolRoute(
    intent_keywords=["dpo", "dynamic performance", "partition compile",
                     "dpo learn", "dpo apply", "dpo reference",
                     "compile acceleration", "parallel compile", "-j4"],
    recipe="simulation_run",
    tool_name="VCS DPO",
    domain="verification",
    binary="vcs",
    command_template=[
        "vcs", "-full64", "-sverilog", "-ntb_opts", "uvm-1.2",
        "-dpo", "-dpo_opts", "mode=learn+apps=default,lint,upfopt,pgates",
        "-dpo_opts", "dbdir=dpo_learndb",
        "-f", "{filelist}", "-o", "simv",
    ],
    run_command=["./simv", "+UVM_TESTNAME={testname}"],
    validation_flags=["-dpo", "-dpo_opts"],
    output_files=["simv", "dpo_learndb/"],
    log_files=["comp_dpo.log"],
    availability_check="VCS_HOME",
    common_args={
        "learn": ["-dpo_opts", "mode=learn+apps=default,lint,upfopt,pgates+dbdir=dpo_learndb"],
        "apply": ["-dpo_opts", "reco_file=dpo_reco.csv"],
        "merge": ["dporg", "merge", "-d", "dpo_learndb"],
        "dump": ["dporg", "dump", "-d", "dpo_learndb"],
    },
    pitfalls=[
        "All modules must be analyzed (vlogan) before DPO compile → unresolved modules",
        "dpo_reco.csv recommendations marked N → must change to Y before apply",
        "DPO requires -lca flag for LCA features",
        "dpo_learndb must exist before apply phase",
    ],
)

TOOL_ROUTES["vcs_ico"] = ToolRoute(
    intent_keywords=["ico", "intelligent coverage", "solver bias",
                     "coverage acceleration", "coverage optimization",
                     "solver bias auto", "solver bias mode",
                     "ntb_solver_bias", "coverage biasing"],
    recipe="simulation_run",
    tool_name="VCS ICO",
    domain="verification",
    binary="vcs",
    command_template=[
        "vcs", "-sverilog", "-ntb_opts", "uvm-1.2",
        "-f", "{filelist}", "-o", "simv",
    ],
    run_command=[
        "./simv", "+UVM_TESTNAME={testname}",
        "+ntb_solver_bias_mode_strategy=nob",
        "+ntb_solver_bias_shared_record=./shared_record",
        "+ntb_solver_bias_wdir=work",
    ],
    validation_flags=["+ntb_solver_bias"],
    output_files=["simv", "shared_record/"],
    log_files=["sim_ico.log"],
    availability_check="VCS_HOME",
    common_args={
        "record_only": ["+ntb_solver_bias_mode_strategy=nob",
                        "+ntb_solver_bias_shared_record=./shared_record",
                        "+ntb_solver_bias_wdir=work"],
        "bias_auto": ["+ntb_solver_bias_mode_auto=5"],
        "bias_bal": ["+ntb_solver_bias_mode_strategy=bal",
                     "+ntb_solver_bias_shared_record=./shared_record"],
        "bias_cov": ["+ntb_solver_bias_mode_strategy=cov",
                     "+ntb_solver_bias_shared_record=./shared_record"],
        "prognosis": ["+ntb_solver_bias_prognosis_config=2",
                      "+ntb_solver_bias_wdir=work_prognosis",
                      "+ntb_solver_bias_test_name={testname}"],
        "report": ["crg", "-dir", "shared_record", "-report", "rpt_name",
                    "-format", "both"],
    },
    pitfalls=[
        "ICO requires shared_record directory for distributed merge",
        "Solver bias mode 0 = disabled (default), 1 = record only, 2+ = biasing",
        "crg report needs shared_record directory from previous run",
        "Prognosis needs multiple seeds for meaningful coverage prediction",
        "+ntb_solver_bias_mode is ignored when auto bias is enabled",
    ],
)
