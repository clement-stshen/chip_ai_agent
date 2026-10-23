"""DV Verification Infrastructure: UVM TB generation, test scheduling,
coverage management, and simulator configuration optimization.

Enhances the existing verification flow with:
  1. Intelligent UVM TB generation (methodology-guided, config-driven)
  2. Dependency-aware test case scheduling (parallel + seed management)
  3. Coverage data collection, merge, analysis, and gap-driven stimulus
  4. Simulator run configuration optimization (VCS DPO/ICO/Verdi RDA)
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import OrderedDict
from pathlib import Path


# ═══════════════════════════════════════════
# 1. UVM TB GENERATOR (methodology-guided)
# ═══════════════════════════════════════════

# Interface signal templates
_IF_SIGNALS = {
    "apb": [
        "input  logic        PCLK",
        "input  logic        PRESETn",
        "input  logic [31:0] PADDR",
        "input  logic [31:0] PWDATA",
        "output logic [31:0] PRDATA",
        "input  logic        PWRITE",
        "input  logic        PENABLE",
        "input  logic        PSEL",
        "output logic        PREADY",
        "output logic        PSLVERR",
    ],
    "axi4": [
        "input  logic        ACLK",
        "input  logic        ARESETn",
        "input  logic [31:0] AWADDR",
        "input  logic [7:0]  AWLEN",
        "input  logic [2:0]  AWSIZE",
        "input  logic        AWVALID",
        "output logic        AWREADY",
        "input  logic [31:0] WDATA",
        "input  logic        WLAST",
        "input  logic        WVALID",
        "output logic        WREADY",
        "input  logic        BVALID",
        "output logic [1:0]  BRESP",
        "output logic        BREADY",
    ],
    "fifo": [
        "input  logic             clk",
        "input  logic             rst_n",
        "input  logic             wren",
        "input  logic             rden",
        "input  logic [DATA_W-1:0] wdata",
        "output logic [DATA_W-1:0] rdata",
        "output logic             full",
        "output logic             empty",
    ],
    "generic": [
        "input  logic             clk",
        "input  logic             rst_n",
        "input  logic             valid",
        "input  logic [DATA_W-1:0] data",
        "output logic             ready",
    ],
}

_COMPONENT_TEMPLATE = {
    "driver": '''class {name}_driver extends uvm_driver #({name}_item);
    `uvm_component_utils({name}_driver)
    virtual {name}_if vif;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if (!uvm_config_db#(virtual {name}_if)::get(this, "", "vif", vif))
            `uvm_fatal("NOVIF", "{name}_driver: vif not set")
    endfunction

    task run_phase(uvm_phase phase);
        {reset_section}
        forever begin
            seq_item_port.get_next_item(req);
            drive_item(req);
            seq_item_port.item_done();
        end
    endtask

    task drive_item({name}_item it);
        repeat (it.delay) @(vif.drv_cb);
        case (it.op)
            {op_write}: begin
                {backpressure_write}
                vif.drv_cb.data <= it.data;
                vif.drv_cb.valid <= 1'b1;
                @(vif.drv_cb);
                vif.drv_cb.valid <= 1'b0;
            end
            {op_read}: begin
                {backpressure_read}
                vif.drv_cb.ready <= 1'b1;
                @(vif.drv_cb);
                vif.drv_cb.ready <= 1'b0;
            end
        endcase
    endtask
endclass
''',
    "monitor": '''class {name}_monitor extends uvm_monitor;
    `uvm_component_utils({name}_monitor)
    virtual {name}_if vif;
    uvm_analysis_port #({name}_item) ap;

    function new(string name, uvm_component parent);
        super.new(name, parent);
        ap = new("ap", this);
    endfunction

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if (!uvm_config_db#(virtual {name}_if)::get(this, "", "vif", vif))
            `uvm_fatal("NOVIF", "{name}_monitor: vif not set")
    endfunction

    task run_phase(uvm_phase phase);
        {name}_item t;
        forever begin
            @(vif.mon_cb);
            if (vif.mon_cb.valid && vif.mon_cb.ready) begin
                t = {name}_item::type_id::create("t");
                t.data = vif.mon_cb.data;
                ap.write(t);
            end
        end
    endtask
endclass
''',
    "agent": '''class {name}_agent extends uvm_agent;
    `uvm_component_utils({name}_agent)
    {name}_driver    drv;
    {name}_monitor   mon;
    uvm_sequencer #({name}_item) sqr;
    uvm_analysis_port #({name}_item) ap;
    uvm_active_passive_enum is_active;

    function new(string name, uvm_component parent);
        super.new(name, parent);
        ap = new("ap", this);
    endfunction

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if (!uvm_config_db#(uvm_active_passive_enum)::get(this, "", "is_active", is_active))
            is_active = UVM_ACTIVE;
        mon = {name}_monitor::type_id::create("mon", this);
        if (is_active == UVM_ACTIVE) begin
            drv = {name}_driver::type_id::create("drv", this);
            sqr = uvm_sequencer#({name}_item)::type_id::create("sqr", this);
        end
    endfunction

    function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        mon.ap.connect(ap);
        if (is_active == UVM_ACTIVE)
            drv.seq_item_port.connect(sqr.seq_item_export);
    endfunction
endclass
''',
    "scoreboard": '''class {name}_scoreboard extends uvm_scoreboard;
    `uvm_component_utils({name}_scoreboard)
    uvm_analysis_imp #({name}_item, {name}_scoreboard) item_imp;

    {name}_item expected_queue[$];
    int mismatches = 0;
    int checks = 0;
    int pass_count = 0;

    function new(string name, uvm_component parent);
        super.new(name, parent);
        item_imp = new("item_imp", this);
    endfunction

    function void write({name}_item t);
        checks++;
        if (expected_queue.size() > 0) begin
            {name}_item e = expected_queue.pop_front();
            if (e.data == t.data) begin
                pass_count++;
            end else begin
                `uvm_error("SB", $sformatf("mismatch exp=0x%0h act=0x%0h", e.data, t.data))
                mismatches++;
            end
        end
    endfunction

    function void check_phase(uvm_phase phase);
        super.check_phase(phase);
        if (mismatches > 0)
            `uvm_error("SB", $sformatf("total mismatches=%0d", mismatches))
        if (expected_queue.size() > 0)
            `uvm_error("SB", $sformatf("%0d expected never observed", expected_queue.size()))
        `uvm_info("SB", $sformatf("checks=%0d pass=%0d fail=%0d remaining=%0d",
                   checks, pass_count, mismatches, expected_queue.size()), UVM_LOW)
    endfunction
endclass
''',
    "env": '''class {name}_env extends uvm_env;
    `uvm_component_utils({name}_env)
    {name}_agent       agent;
    {name}_scoreboard  sb;
    {name}_coverage    cov;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        agent = {name}_agent::type_id::create("agent", this);
        sb    = {name}_scoreboard::type_id::create("sb", this);
        cov   = {name}_coverage::type_id::create("cov", this);
    endfunction

    function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        agent.ap.connect(sb.item_imp);
        agent.ap.connect(cov.analysis_export);
    endfunction
endclass
''',
    "coverage": '''class {name}_coverage extends uvm_subscriber #({name}_item);
    `uvm_component_utils({name}_coverage)
    uvm_analysis_export #({name}_item) analysis_export;
    `uvm_analysis_imp_decl(_cov)

    covergroup cg_{name};
        option.per_instance = 1;
        cp_op: coverpoint item.op;
        cp_data: coverpoint item.data {{ bins low = {{[0:63]}}; bins mid = {{[64:127]}}; bins high = {{[128:255]}}; }}
        cross_op_data: cross cp_op, cp_data;
    endgroup

    function new(string name, uvm_component parent);
        super.new(name, parent);
        analysis_export = new("analysis_export", this);
        cg_{name} = new();
    endfunction

    function void write_cov({name}_item t);
        item = t;
        cg_{name}.sample();
    endfunction

    function void report_phase(uvm_phase phase);
        super.report_phase(phase);
        `uvm_info("COV", $sformatf("{name} coverage: %.2f%%", cg_{name}.get_coverage()), UVM_LOW)
    endfunction
endclass
''',
    "test": '''class {name}_base_test extends uvm_test;
    `uvm_component_utils({name}_base_test)
    {name}_env env;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        env = {name}_env::type_id::create("env", this);
    endfunction

    virtual task do_stimulus();
    endtask

    task run_phase(uvm_phase phase);
        phase.raise_objection(this);
        do_stimulus();
        #100ns;
        phase.drop_objection(this);
    endtask

    function void report_phase(uvm_phase phase);
        uvm_report_server rs;
        super.report_phase(phase);
        rs = uvm_report_server::get_server();
        if (rs.get_severity_count(UVM_ERROR) == 0 &&
            rs.get_severity_count(UVM_FATAL) == 0)
            `uvm_info(get_type_name(), "** TEST PASSED **", UVM_LOW)
        else
            `uvm_info(get_type_name(), "** TEST FAILED **", UVM_LOW)
    endfunction
endclass

class {name}_smoke_test extends {name}_base_test;
    `uvm_component_utils({name}_smoke_test)
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction
    virtual task do_stimulus();
        {name}_base_seq seq = {name}_base_seq::type_id::create("seq");
        if (!seq.randomize() with {{ n_items == 25; }})
            `uvm_fatal(get_type_name(), "seq randomize failed")
        seq.start(env.agent.sqr);
    endtask
endclass

class {name}_random_test extends {name}_base_test;
    `uvm_component_utils({name}_random_test)
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction
    virtual task do_stimulus();
        repeat (3) begin
            {name}_base_seq seq = {name}_base_seq::type_id::create("seq");
            if (!seq.randomize())
                `uvm_fatal(get_type_name(), "seq randomize failed")
            seq.start(env.agent.sqr);
        end
    endtask
endclass
''',
}


def generate_uvm_tb(name: str, interface_type: str = "generic",
                    data_width: int = 8, components: list[str] | None = None,
                    output_dir: str | None = None) -> dict:
    """Generate a complete UVM testbench from methodology patterns.

    Args:
        name: DUT/component name (e.g., "fifo", "apb", "uart")
        interface_type: Signal template ("apb", "axi4", "fifo", "generic")
        data_width: Data bus width
        components: Which components to generate (default: all)
        output_dir: Output directory for generated files

    Returns:
        {"files": {filename: content}, "filelist": [...], "methodology_checklist": [...]}
    """
    from chip_ai_agent import uvm_methodology as um

    components = components or ["interface", "package", "driver", "monitor",
                                 "agent", "scoreboard", "coverage", "env", "test", "tb_top"]
    files = {}

    # Interface
    if "interface" in components:
        signals = _IF_SIGNALS.get(interface_type, _IF_SIGNALS["generic"])
        sig_str = ",\n    ".join(signals)
        files[f"{name}_if.sv"] = f'''interface {name}_if #(parameter int DATA_W = {data_width}) (input logic clk);
    logic rst_n;
    logic valid;
    logic ready;
    logic [DATA_W-1:0] data;

    clocking drv_cb @(posedge clk);
        default input #1step output #1;
        output valid, ready, data;
        input  full, empty;
    endclocking

    clocking mon_cb @(posedge clk);
        default input #1step;
        input valid, ready, data;
    endclocking

    modport drv (clocking drv_cb, input rst_n);
    modport mon (clocking mon_cb, input rst_n);
endinterface
'''

    # Package (item + sequence)
    if "package" in components:
        files[f"{name}_pkg.sv"] = f'''`include "uvm_macros.svh"
package {name}_pkg;
    import uvm_pkg::*;

    parameter int {name.upper()}_DATA_W = {data_width};

    typedef enum bit {{{name.upper()}_WRITE, {name.upper()}_READ}} {name}_op_e;

    class {name}_item extends uvm_sequence_item;
        rand {name}_op_e op;
        rand bit [{data_width}-1:0] data;
        rand int unsigned delay;
        constraint c_delay {{ delay inside {{[0:3]}}; }}
        constraint c_dist {{ op dist {{ {name.upper()}_WRITE := 50, {name.upper()}_READ := 50 }}; }}
        `uvm_object_utils_begin({name}_item)
            `uvm_field_enum({name}_op_e, op, UVM_ALL_ON)
            `uvm_field_int(data, UVM_ALL_ON)
        `uvm_object_utils_end
        function new(string name = "{name}_item"); super.new(name); endfunction
    endclass

    class {name}_base_seq extends uvm_sequence #({name}_item);
        rand int unsigned n_items;
        constraint c_n {{ n_items inside {{[20:100]}}; }}
        `uvm_object_utils_begin({name}_base_seq)
            `uvm_field_int(n_items, UVM_ALL_ON)
        `uvm_object_utils_end
        function new(string name = "{name}_base_seq"); super.new(name); endfunction
        task body();
            {name}_item it;
            repeat (n_items) begin
                it = {name}_item::type_id::create("it");
                start_item(it);
                if (!it.randomize()) `uvm_fatal(get_type_name(), "randomize failed")
                finish_item(it);
            end
        endtask
    endclass
endpackage
'''

    # Components from methodology templates
    tpl_vars = {
        "name": name,
        "op_write": f"{name.upper()}_WRITE",
        "op_read": f"{name.upper()}_READ",
        "reset_section": f"vif.drv_cb.valid <= 1'b0; vif.drv_cb.ready <= 1'b0;",
        "backpressure_write": "while (vif.drv_cb.full) @(vif.drv_cb);",
        "backpressure_read": "while (vif.drv_cb.empty) @(vif.drv_cb);",
    }
    for comp in ["driver", "monitor", "agent", "scoreboard", "env", "coverage", "test"]:
        if comp in components and comp in _COMPONENT_TEMPLATE:
            files[f"{name}_{comp}.sv"] = _COMPONENT_TEMPLATE[comp].format(**tpl_vars)

    # tb_top
    if "tb_top" in components:
        files["tb_top.sv"] = f'''`include "uvm_macros.svh"
module tb_top;
    import uvm_pkg::*;
    import {name}_pkg::*;

    logic clk;
    initial begin clk = 0; forever #5ns clk = ~clk; end

    {name}_if #({data_width}) vif (clk);

    initial begin
        vif.rst_n = 0;
        repeat (5) @(posedge clk);
        vif.rst_n = 1;
    end

    initial begin
        uvm_config_db#(virtual {name}_if #({data_width}))::set(null, "*", "vif", vif);
        run_test();
    end

    initial begin
        $fsdbDumpfile("{name}_tb.fsdb");
        $fsdbDumpvars(0, tb_top);
    end
endmodule
'''

    # Generate filelist
    filelist = [f"../rtl/{name}.sv"] + [f"../tb/{f}" for f in files.keys()]
    files["filelist.f"] = "\n".join(filelist)

    # Get methodology checklist
    checklist = um.get_checklist("block_level")

    return {
        "files": files,
        "filelist": filelist,
        "methodology_checklist": checklist.get("items", []),
        "components_generated": [c for c in components if c in files or any(c in f for f in files)],
    }


# ═══════════════════════════════════════════
# 2. TEST SCHEDULER (dependency-aware, parallel)
# ═══════════════════════════════════════════

def create_test_plan(tests: list[dict], simulator: str = "vcs",
                     seeds: list[int] | None = None,
                     max_parallel: int = 4) -> dict:
    """Create a structured test plan with seeds and dependency ordering.

    Args:
        tests: [{"name": "test_x", "depends_on": ["test_y"], "priority": 1}, ...]
        simulator: "vcs" or "questa" or "xcelium"
        seeds: List of random seeds for each test
        max_parallel: Max concurrent simulations
    """
    seeds = seeds or [1, 42, 7]
    plan = {
        "simulator": simulator,
        "max_parallel": max_parallel,
        "total_runs": len(tests) * len(seeds),
        "tests": [],
        "phases": [],
    }

    # Build dependency graph
    test_map = {t["name"]: t for t in tests}
    visited = set()
    phases = []

    def resolve_deps(test, depth=0):
        if test["name"] in visited:
            return
        visited.add(test["name"])
        for dep in test.get("depends_on", []):
            if dep in test_map:
                resolve_deps(test_map[dep], depth + 1)
        phases.append(test["name"])

    for t in tests:
        resolve_deps(t)

    # Group into phases (tests that can run in parallel)
    phase_groups = []
    remaining = list(dict.fromkeys(phases))  # deduplicate, preserve order
    scheduled = set()
    while remaining:
        ready = [t for t in remaining
                 if all(d in scheduled for d in test_map.get(t, {}).get("depends_on", []))]
        if not ready:
            ready = [remaining[0]]  # break deadlock
        phase_groups.append(ready)
        scheduled.update(ready)
        remaining = [t for t in remaining if t not in scheduled]

    for i, phase in enumerate(phase_groups):
        for test_name in phase:
            for seed in seeds:
                plan["tests"].append({
                    "phase": i,
                    "test": test_name,
                    "seed": seed,
                    "run_name": f"{test_name}_s{seed}",
                    "cm_name": f"{test_name}_s{seed}",
                    "priority": test_map.get(test_name, {}).get("priority", 1),
                })

    plan["phase_count"] = len(phase_groups)
    plan["phases"] = phase_groups
    return plan


# ═══════════════════════════════════════════
# 3. COVERAGE MANAGER
# ═══════════════════════════════════════════

def parse_coverage_log(log_content: str) -> dict:
    """Parse coverage data from simulation log."""
    result = {
        "overall_pct": 0.0,
        "line_pct": 0.0,
        "cond_pct": 0.0,
        "fsm_pct": 0.0,
        "toggle_pct": 0.0,
        "branch_pct": 0.0,
        "assert_pct": 0.0,
        "covergroups": [],
        "uncovered_bins": [],
    }

    # Extract coverage percentage
    m = re.search(r"coverage:\s*([\d.]+)%", log_content)
    if m:
        result["overall_pct"] = float(m.group(1))

    # Extract scoreboard data
    m = re.search(r"checks=(\d+)\s+pass=(\d+)\s+fail=(\d+)\s+remaining=(\d+)", log_content)
    if m:
        result["scoreboard"] = {
            "checks": int(m.group(1)),
            "passed": int(m.group(2)),
            "failed": int(m.group(3)),
            "remaining": int(m.group(4)),
        }

    # Extract UVM report counts
    for sev in ["UVM_ERROR", "UVM_FATAL", "UVM_WARNING", "UVM_INFO"]:
        m = re.search(rf"{sev}\s*:\s*(\d+)", log_content)
        if m:
            result[sev.lower()] = int(m.group(1))

    return result


def create_coverage_plan(coverage_data: dict, target_pct: float = 90.0) -> dict:
    """Create a coverage closure plan based on current coverage data."""
    current = coverage_data.get("overall_pct", 0.0)
    gap = target_pct - current
    plan = {
        "current_pct": current,
        "target_pct": target_pct,
        "gap": round(gap, 1),
        "status": "CLOSED" if gap <= 0 else "OPEN",
        "recommendations": [],
    }

    if gap > 0:
        # Analyze uncovered areas
        if current < 50:
            plan["recommendations"] = [
                "Add more random seeds (increase regression count)",
                "Enable ICO auto bias mode 5-8 for coverage acceleration",
                "Check for unreachable code/bins (add exclusions)",
            ]
        elif current < 70:
            plan["recommendations"] = [
                "Add directed tests for corner cases (full/empty boundary)",
                "Enable cross coverage for interaction scenarios",
                "Use ICO prognosis to predict coverage from additional seeds",
            ]
        elif current < target_pct:
            plan["recommendations"] = [
                "Review uncovered bins — likely rare corner cases",
                "Add targeted stimulus for specific uncovered bins",
                "Consider waiving unreachable bins with justification",
            ]

    return plan


# ═══════════════════════════════════════════
# 4. SIMULATOR CONFIG OPTIMIZATION
# ═══════════════════════════════════════════

_SIM_CONFIGS = OrderedDict([
    ("baseline", {
        "description": "Standard compile+sim (no optimizations)",
        "compile_args": ["-full64", "-sverilog", "-timescale=1ns/1ps",
                         "-ntb_opts", "uvm-1.2", "-debug_access+all"],
        "sim_args": ["+UVM_VERBOSITY=UVM_MEDIUM"],
        "expected_speedup": "1.0x",
    }),
    ("dpo_parallel", {
        "description": "DPO parallel compile (-j4)",
        "compile_args": ["-full64", "-sverilog", "-timescale=1ns/1ps",
                         "-ntb_opts", "uvm-1.2", "-debug_access+all", "-j4"],
        "sim_args": ["+UVM_VERBOSITY=UVM_MEDIUM"],
        "expected_speedup": "1.2x compile",
    }),
    ("ico_bias5", {
        "description": "ICO solver bias auto=5 (coverage acceleration)",
        "compile_args": ["-full64", "-sverilog", "-timescale=1ns/1ps",
                         "-ntb_opts", "uvm-1.2", "-debug_access+all"],
        "sim_args": ["+UVM_VERBOSITY=UVM_MEDIUM", "+ntb_solver_bias_mode_auto=5"],
        "expected_speedup": "1.2x coverage closure",
    }),
    ("dpo_ico", {
        "description": "DPO+ICO combined (compile + coverage acceleration)",
        "compile_args": ["-full64", "-sverilog", "-timescale=1ns/1ps",
                         "-ntb_opts", "uvm-1.2", "-debug_access+all", "-j4"],
        "sim_args": ["+UVM_VERBOSITY=UVM_MEDIUM", "+ntb_solver_bias_mode_auto=5"],
        "expected_speedup": "1.3x combined",
    }),
    ("coverage_full", {
        "description": "Full coverage (line+cond+fsm+tgl+branch+assert)",
        "compile_args": ["-full64", "-sverilog", "-timescale=1ns/1ps",
                         "-ntb_opts", "uvm-1.2", "-debug_access+all",
                         "-cm", "line+cond+fsm+tgl+branch+assert"],
        "sim_args": ["+UVM_VERBOSITY=UVM_MEDIUM",
                     "-cm", "line+cond+fsm+tgl+branch+assert"],
        "expected_speedup": "1.0x (coverage overhead)",
    }),
    ("fsdb_debug", {
        "description": "FSDB debug mode (for Verdi RDA)",
        "compile_args": ["-full64", "-sverilog", "-timescale=1ns/1ps",
                         "-ntb_opts", "uvm-1.2",
                         "+define+UVM_VERDI_PORT_RECORDING",
                         "-lca", "-kdb", "-debug_access+all+reverse", "+vpi"],
        "sim_args": ["+UVM_VERBOSITY=UVM_MEDIUM"],
        "expected_speedup": "0.5x (debug overhead, for debug only)",
    }),
])


def get_sim_config(config_name: str, extra_compile: list[str] | None = None,
                   extra_sim: list[str] | None = None) -> dict:
    """Get simulator configuration with optional extra args."""
    if config_name not in _SIM_CONFIGS:
        return {"error": f"unknown config: {config_name}",
                "available": list(_SIM_CONFIGS.keys())}
    cfg = dict(_SIM_CONFIGS[config_name])
    cfg["name"] = config_name
    if extra_compile:
        cfg["compile_args"] = cfg["compile_args"] + extra_compile
    if extra_sim:
        cfg["sim_args"] = cfg["sim_args"] + extra_sim
    return cfg


def compare_sim_configs() -> list[dict]:
    """Compare all simulator configurations."""
    return [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "compile_args" and kk != "sim_args"}}
            for k, v in _SIM_CONFIGS.items()]
