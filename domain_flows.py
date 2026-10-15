"""Machine-readable per-domain flows, code-enforced from the 16 vendored
digital-chip-design-agents orchestrators (stage sequences, loop-back rules
with caps, sign-off gates, escalation rules, tool routing).

This is the single source of truth the DesignPipeline engine executes;
the markdown orchestrators remain the human/LLM-readable contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoopBack:
    stage: str
    failure_class: str
    goto: str
    cap: int                      # -1 = unlimited
    note: str = ""


@dataclass(frozen=True)
class Escalation:
    stage: str
    trigger: str                  # human-readable trigger
    failure_class: str = "functional"
    fix_request: bool = False     # write fix_request + hand to pipeline driver


@dataclass(frozen=True)
class DomainFlow:
    domain: str
    skill: str
    stages: list[str]
    loop_backs: list[LoopBack] = field(default_factory=list)
    escalations: list[Escalation] = field(default_factory=list)
    signoff_gates: dict[str, str] = field(default_factory=dict)
    checkpoint_stage: str = ""    # sign-off stage holding the human gate
    tools_oss: list[str] = field(default_factory=list)
    tools_proprietary: list[str] = field(default_factory=list)
    wrapper: str | None = None    # vendored output-compression wrapper

    def loop_back_for(self, stage: str, failure_class: str) -> LoopBack | None:
        for lb in self.loop_backs:
            if lb.stage == stage and lb.failure_class == failure_class:
                return lb
        return None


DOMAIN_FLOWS: dict[str, DomainFlow] = {f.domain: f for f in [
    DomainFlow(
        domain="architecture", skill="architecture",
        stages=["spec_analysis", "arch_exploration", "perf_modelling",
                "power_area_estimation", "risk_assessment", "arch_signoff"],
        loop_backs=[
            LoopBack("perf_modelling", "timing", "arch_exploration", 3,
                     "throughput misses target"),
            LoopBack("power_area_estimation", "power_area", "arch_exploration", 2,
                     "area or power > 80% budget"),
            LoopBack("risk_assessment", "spec_gap", "risk_assessment", 2,
                     "HIGH risks unmitigated"),
            LoopBack("arch_signoff", "spec_gap", "spec_analysis", 1,
                     "spec coverage gap"),
            LoopBack("arch_signoff", "timing", "arch_exploration", 2, "PPA gap"),
            LoopBack("arch_signoff", "power_area", "arch_exploration", 2, "PPA gap"),
        ],
        signoff_gates={
            "spec_coverage_pct": ">= 100",
            "ppa_within_budget": "== true",
            "high_risks_open": "== 0",
        },
        checkpoint_stage="arch_signoff",
        tools_oss=["python3", "gem5", "mcpat", "cacti"],
        tools_proprietary=["Platform Architect", "VSP"],
        wrapper="gem5",
    ),
    DomainFlow(
        domain="rtl-design", skill="rtl-design",
        stages=["module_planning", "rtl_coding", "lint_check",
                "cdc_rdc_analysis", "synth_check", "rtl_signoff"],
        loop_backs=[
            LoopBack("lint_check", "tool_error", "rtl_coding", 5, "lint errors > 0"),
            LoopBack("cdc_rdc_analysis", "connectivity", "rtl_coding", 3,
                     "unwaived CDC/RDC violations"),
            LoopBack("synth_check", "timing", "rtl_coding", 2, "WNS < -0.5 ns"),
            LoopBack("synth_check", "power_area", "module_planning", 1,
                     "area > 120% estimate"),
            LoopBack("rtl_signoff", "spec_gap", "module_planning", 1,
                     "missing modules"),
            LoopBack("rtl_signoff", "functional", "rtl_coding", 2, "quality issues"),
        ],
        signoff_gates={
            "lint_errors": "== 0",
            "cdc_violations_unwaived": "== 0",
            "all_modules_implemented": "== true",
        },
        checkpoint_stage="rtl_signoff",
        tools_oss=["verilator", "slang", "surelog", "sv2v", "iverilog"],
        tools_proprietary=["spyglass", "jg (CDC)", "questa cdc"],
        wrapper="verilator-sim",
    ),
    DomainFlow(
        domain="verification", skill="functional-verification",
        stages=["tb_architecture", "test_planning", "uvm_tb_build",
                "directed_tests", "constrained_random", "coverage_analysis",
                "formal_assist", "regression_signoff"],
        loop_backs=[
            LoopBack("uvm_tb_build", "tool_error", "uvm_tb_build", 3),
            LoopBack("uvm_tb_build", "functional", "uvm_tb_build", 3),
            LoopBack("coverage_analysis", "coverage_gap", "constrained_random", 5,
                     "functional coverage < 100%"),
            LoopBack("coverage_analysis", "tool_error", "directed_tests", 3,
                     "code line coverage < 95%"),
            LoopBack("regression_signoff", "functional", "constrained_random", 3,
                     "failure rate > 0%"),
        ],
        escalations=[
            Escalation("directed_tests", "DUT bug found", "functional",
                       fix_request=True),
        ],
        signoff_gates={
            "functional_coverage_pct": "== 100",
            "regression_failures": "== 0",
            "open_p0_bugs": "== 0",
            "uvm_fatal_count": "== 0",
        },
        checkpoint_stage="regression_signoff",
        tools_oss=["verilator", "iverilog", "cocotb", "pyuvm", "uvvm"],
        tools_proprietary=["vcs", "xrun", "vsim"],
        wrapper="verilator-sim",
    ),
    DomainFlow(
        domain="formal", skill="formal-verification",
        stages=["property_planning", "environment_setup", "fpv_run",
                "cex_analysis", "lec_run", "formal_signoff"],
        loop_backs=[
            LoopBack("fpv_run", "spec_gap", "environment_setup", 3,
                     "vacuous proof"),
            LoopBack("fpv_run", "tool_error", "fpv_run", 3,
                     "inconclusive — increase bound"),
            LoopBack("lec_run", "connectivity", "lec_run", 3,
                     "unmatched points"),
        ],
        escalations=[
            Escalation("fpv_run", "CEX found (RTL bug)", "functional",
                       fix_request=True),
        ],
        signoff_gates={
            "unproven_p0_properties": "== 0",
            "lec_unmatched_points": "== 0",
            "vacuous_proofs": "== 0",
        },
        checkpoint_stage="formal_signoff",
        tools_oss=["sby", "yosys", "boolector", "z3", "abc"],
        tools_proprietary=["jg", "vcf", "qforma"],
        wrapper="symbiflow",
    ),
    DomainFlow(
        domain="synthesis", skill="logic-synthesis",
        stages=["constraint_setup", "compile_explore", "compile_final",
                "netlist_qc", "synthesis_signoff"],
        loop_backs=[
            LoopBack("compile_final", "timing", "compile_final", 3, "WNS < 0"),
            LoopBack("compile_final", "power_area", "compile_explore", 2,
                     "area > budget"),
            LoopBack("netlist_qc", "connectivity", "compile_final", 2,
                     "LEC unmatched"),
            LoopBack("netlist_qc", "tool_error", "compile_final", 2,
                     "unmapped cells"),
        ],
        signoff_gates={
            "wns_ns": ">= constraints.timing.wns_ns_target (default 0)",
            "lec_unmatched_points": "== 0",
            "unmapped_cells": "== 0",
        },
        checkpoint_stage="synthesis_signoff",
        tools_oss=["yosys", "surelog", "abc"],
        tools_proprietary=["dc_shell", "genus", "fc_shell"],
        wrapper="yosys",
    ),
    DomainFlow(
        domain="dft", skill="dft",
        stages=["dft_architecture", "scan_insertion", "atpg", "bist_insertion",
                "jtag_setup", "dft_signoff"],
        loop_backs=[
            LoopBack("scan_insertion", "drc_lvs", "scan_insertion", 3,
                     "scan DRC errors > 0"),
            LoopBack("atpg", "coverage_gap", "scan_insertion", 2,
                     "SAF coverage < target"),
            LoopBack("dft_signoff", "functional", "bist_insertion", 2, "BIST fail"),
            LoopBack("dft_signoff", "connectivity", "jtag_setup", 2,
                     "JTAG connectivity fail"),
        ],
        signoff_gates={
            "scan_drc_errors": "== 0",
            "saf_coverage_pct": ">= 99.0",
            "bist_pass": "== true",
            "jtag_connectivity": "== pass",
        },
        checkpoint_stage="dft_signoff",
        tools_oss=["yosys", "openroad"],
        tools_proprietary=["tmax", "modus", "tessent"],
        wrapper="yosys",
    ),
    DomainFlow(
        domain="sta", skill="sta",
        stages=["constraint_validation", "multi_corner_analysis", "path_analysis",
                "exception_review", "eco_guidance", "sta_signoff"],
        loop_backs=[
            LoopBack("path_analysis", "timing", "exception_review", -1,
                     "violations found"),
            LoopBack("exception_review", "spec_gap", "path_analysis", 3,
                     "invalid exceptions"),
            LoopBack("eco_guidance", "timing", "multi_corner_analysis", 10,
                     "ECO applied — re-query corners (session MCP)"),
        ],
        escalations=[
            Escalation("eco_guidance", "ECO cell count > 2%", "resource_limit"),
        ],
        signoff_gates={
            "setup_wns_ns": ">= constraints.timing.wns_ns_target at all corners",
            "hold_wns_ps": ">= constraints.timing.hold target",
            "setup_tns_ps": "<= constraints.timing.tns target",
            "hold_tns_ps": "<= constraints.timing hold tns target",
        },
        checkpoint_stage="sta_signoff",
        tools_oss=["sta (OpenSTA)", "openroad"],
        tools_proprietary=["pt_shell", "tempus"],
        wrapper="opensta",
    ),
    DomainFlow(
        domain="pd", skill="physical-design",
        stages=["floorplan", "placement", "cts", "routing",
                "timing_optimization", "power_optimization", "area_optimization",
                "signoff"],
        loop_backs=[
            LoopBack("placement", "timing", "floorplan", 2, "WNS < -0.5 ns"),
            LoopBack("routing", "drc_lvs", "routing", 3, "DRC violations > 0"),
            LoopBack("routing", "timing", "timing_optimization", 3, "WNS < 0"),
            LoopBack("timing_optimization", "resource_limit", "routing", 1,
                     "ECO > 2% cells"),
            LoopBack("signoff", "timing", "timing_optimization", 2),
            LoopBack("signoff", "drc_lvs", "routing", 2),
            LoopBack("signoff", "power_area", "power_optimization", 1,
                     "power/EM"),
        ],
        signoff_gates={
            "setup_wns_ns": ">= target (default 0)",
            "hold_wns_ps": ">= target",
            "setup_tns_ps": "<= target",
            "drc_violations": "== 0",
            "lvs_errors": "== 0",
            "antenna_violations": "== 0",
            "core_area_util_pct": "<= constraints.area max (default 85)",
        },
        checkpoint_stage="signoff",
        tools_oss=["openroad", "librelane", "klayout"],
        tools_proprietary=["innovus", "icc2"],
        wrapper="openroad",
    ),
    DomainFlow(
        domain="hls", skill="hls",
        stages=["algorithm_analysis", "directive_planning", "hls_synthesis",
                "rtl_qc", "cosimulation", "hls_signoff"],
        loop_backs=[
            LoopBack("hls_synthesis", "timing", "directive_planning", 4,
                     "latency > target"),
            LoopBack("hls_synthesis", "power_area", "directive_planning", 3,
                     "area > budget"),
            LoopBack("hls_synthesis", "functional", "directive_planning", 3,
                     "II > target"),
            LoopBack("cosimulation", "functional", "algorithm_analysis", 2,
                     "output mismatch"),
            LoopBack("rtl_qc", "tool_error", "directive_planning", 2,
                     "latch inferred"),
        ],
        signoff_gates={
            "cosim_match": "== true",
            "latch_count": "== 0",
            "latency_meets_target": "== true",
            "area_within_budget": "== true",
        },
        checkpoint_stage="hls_signoff",
        tools_oss=["bambu", "legup", "calyx"],
        tools_proprietary=["catapult", "vitis_hls", "stratus"],
        wrapper="bambu",
    ),
    DomainFlow(
        domain="soc", skill="soc-integration",
        stages=["ip_procurement", "ip_configuration", "bus_fabric_setup",
                "top_integration", "chip_level_sim", "integration_signoff"],
        loop_backs=[
            LoopBack("ip_configuration", "timing", "ip_procurement", 2,
                     "timing/interface error"),
            LoopBack("top_integration", "connectivity", "top_integration", 3,
                     "connectivity errors"),
            LoopBack("chip_level_sim", "functional", "top_integration", 3,
                     "peripheral test fail"),
            LoopBack("chip_level_sim", "connectivity", "bus_fabric_setup", 2,
                     "bus protocol violation"),
        ],
        signoff_gates={
            "connectivity_errors": "== 0",
            "sim_pass_rate_pct": "== 100",
            "axi_protocol_violations": "== 0",
            "unqualified_ips": "== 0",
        },
        checkpoint_stage="integration_signoff",
        tools_oss=["verilator", "cocotb", "fusesoc"],
        tools_proprietary=["vcs", "xrun", "vsim"],
        wrapper="verilator-sim",
    ),
    DomainFlow(
        domain="memory-ip", skill="memory-ip-design",
        stages=["memory_requirements", "macro_selection", "array_architecture",
                "redundancy_repair", "view_generation", "integration_prep",
                "memory_signoff"],
        loop_backs=[
            LoopBack("macro_selection", "timing", "memory_requirements", 2,
                     "no candidate meets access time"),
            LoopBack("array_architecture", "power_area", "macro_selection", 3,
                     "area > 120% budget"),
            LoopBack("array_architecture", "timing", "memory_requirements", 1,
                     "bandwidth < target"),
            LoopBack("redundancy_repair", "functional", "array_architecture", 2,
                     "projected yield < target"),
            LoopBack("view_generation", "tool_error", "macro_selection", 2,
                     "view QA errors > 0"),
            LoopBack("integration_prep", "drc_lvs", "array_architecture", 2,
                     "placement/channel infeasible"),
            LoopBack("memory_signoff", "timing", "array_architecture", 1,
                     "Vmin margin short"),
        ],
        signoff_gates={
            "view_qa_errors": "== 0",
            "all_corners_characterized": "== true",
            "redundancy_allocated": "== true",
            "mbist_ports_exposed": "== true",
            "projected_repair_yield_pct": ">= constraints.memory_ip target",
            "vmin_margin_mv": ">= constraints.memory_ip target",
        },
        checkpoint_stage="memory_signoff",
        tools_oss=["openram", "cacti", "sky130/gf180mcu macros"],
        tools_proprietary=["compiler: memory compiler"],
        wrapper=None,
    ),
    DomainFlow(
        domain="compiler", skill="compiler-toolchain",
        stages=["isa_analysis", "backend_dev", "assembler_dev", "linker_config",
                "runtime_libs", "toolchain_validation", "toolchain_signoff"],
        loop_backs=[
            LoopBack("backend_dev", "tool_error", "backend_dev", 5,
                     "codegen errors > 0"),
            LoopBack("assembler_dev", "tool_error", "assembler_dev", 3,
                     "encoding errors"),
            LoopBack("linker_config", "tool_error", "linker_config", 3,
                     "unresolved symbols"),
            LoopBack("runtime_libs", "functional", "runtime_libs", 3,
                     "lib test fail"),
            LoopBack("toolchain_validation", "functional", "backend_dev", 3,
                     "pass rate < 95%"),
        ],
        signoff_gates={
            "compiler_regression_pass_pct": ">= 99",
            "runtime_test_pass_pct": ">= 99",
            "miscompilation_count": "== 0",
        },
        checkpoint_stage="toolchain_signoff",
        tools_oss=["clang", "llc", "llvm-mc", "gcc", "qemu"],
        tools_proprietary=[],
        wrapper=None,
    ),
    DomainFlow(
        domain="firmware", skill="embedded-firmware",
        stages=["bsp_development", "peripheral_drivers", "rtos_integration",
                "driver_validation", "system_integration", "firmware_signoff"],
        loop_backs=[
            LoopBack("peripheral_drivers", "functional", "peripheral_drivers", 3),
            LoopBack("rtos_integration", "functional", "rtos_integration", 3,
                     "deadlock/overflow"),
            LoopBack("driver_validation", "functional", "peripheral_drivers", 3),
            LoopBack("system_integration", "functional", "peripheral_drivers", 2),
        ],
        signoff_gates={
            "all_driver_tests_pass": "== true",
            "stress_test_24h_clean": "== true",
            "open_p0_bugs": "== 0",
        },
        checkpoint_stage="firmware_signoff",
        tools_oss=["arm-none-eabi-gcc", "riscv64-unknown-elf-gcc", "openocd", "gdb"],
        tools_proprietary=[],
        wrapper=None,
    ),
    DomainFlow(
        domain="fpga", skill="fpga-emulation",
        stages=["rtl_adaptation", "partitioning", "fpga_synthesis", "bring_up",
                "sw_validation", "proto_signoff"],
        loop_backs=[
            LoopBack("fpga_synthesis", "timing", "rtl_adaptation", 3,
                     "WNS < -0.5 ns — add pipeline regs"),
            LoopBack("fpga_synthesis", "power_area", "partitioning", 2,
                     "utilisation > 70%"),
            LoopBack("bring_up", "functional", "rtl_adaptation", 2,
                     "peripheral not responding"),
            LoopBack("sw_validation", "functional", "rtl_adaptation", -1,
                     "HW bug found — RTL-gated"),
        ],
        escalations=[
            Escalation("sw_validation", "HW bug found", "functional",
                       fix_request=True),
        ],
        signoff_gates={
            "all_driver_tests_pass": "== true",
            "stress_4h_clean": "== true",
            "hw_bugs_filed_to_rtl": "== true",
        },
        checkpoint_stage="proto_signoff",
        tools_oss=["yosys", "nextpnr", "openFPGALoader"],
        tools_proprietary=["vivado", "quartus"],
        wrapper=None,
    ),
    DomainFlow(
        domain="infrastructure", skill="infrastructure",
        stages=["tool_discovery", "module_discovery", "tool_installation",
                "wrapper_deployment", "mcp_configuration",
                "environment_validation"],
        loop_backs=[
            LoopBack("environment_validation", "tool_error", "tool_installation", 2,
                     "critical tool MISSING"),
        ],
        escalations=[
            Escalation("tool_installation", "python3 missing", "tool_error"),
            Escalation("wrapper_deployment", "permission denied", "tool_error"),
        ],
        signoff_gates={
            "tools_detected": ">= planned set",
            "wrappers_executable": "== 8/8",
            "mcp_configs_written": "== 10/10",
        },
        checkpoint_stage="environment_validation",
        tools_oss=["python3", "verilator", "yosys", "openroad", "sta", "klayout",
                   "sby", "gem5", "bambu", "nextpnr"],
        tools_proprietary=[],
        wrapper=None,
    ),
]}


# ---------------------------------------------------------------- spec→tapeout
MAINLINE: list[str] = [
    "architecture", "rtl-design", "hls", "verification", "formal",
    "synthesis", "dft", "pd", "sta",
]
# optional branches keyed by insertion point (run after that mainline domain)
BRANCHES: dict[str, list[str]] = {
    "rtl-design": ["soc", "memory-ip", "compiler"],
    "verification": ["firmware", "fpga"],
}


def flow(domain: str) -> DomainFlow:
    try:
        return DOMAIN_FLOWS[domain]
    except KeyError:
        raise ValueError(f"unknown domain: {domain!r} "
                         f"(valid: {', '.join(DOMAIN_FLOWS)})") from None


def pipeline_plan(include_branches: bool = True) -> list[dict]:
    """spec → tape-out ordering with per-domain metadata."""
    out: list[dict] = []
    for d in MAINLINE:
        out.append({"domain": d, "kind": "mainline", **_meta(d)})
        if include_branches:
            for b in BRANCHES.get(d, []):
                out.append({"domain": b, "kind": "branch", **_meta(b)})
    return out


def _meta(d: str) -> dict:
    f = DOMAIN_FLOWS[d]
    return {"skill": f.skill, "stages": f.stages,
            "checkpoint": f.checkpoint_stage,
            "signoff_gates": f.signoff_gates}
