"""UVM 1.2 methodology decision layer: structured patterns, phase maps,
component recipes, and pitfalls that the agent can query to guide testbench
construction.  This is the "how to use UVM" complement to the "what is UVM"
tools (chip_uvm_semantic/explain) and the "is it compliant" checker.

Each pattern is a self-contained dict with:
- ``pattern``:   component type key (driver / monitor / agent / scoreboard / ...)
- ``decision``:  when to use this pattern vs alternatives
- ``phases``:    exact (phase → action) mapping for this component
- ``code_skel``: minimal compilable skeleton (SystemVerilog)
- ``connects``:  TLM / config_db connection edges
- ``pitfalls``:  common mistakes and their fixes
- ``refs``:      source class, manual doc, and concept-card cross-references
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------------------
# Phase decision map: what goes in which phase (globally valid, not per-component)
# ---------------------------------------------------------------------------
PHASE_MAP = OrderedDict([
    ("build_phase", {
        "type": "function", "direction": "top-down", "time_cost": "zero",
        "actions": [
            "uvm_component::create() all child components",
            "uvm_config_db#(T)::get() virtual interfaces and parameters",
            "uvm_config_db#(T)::set() if this is a parent configuring children",
            "factory type/instance overrides (must precede super.build_phase)",
            "allocate / initialize class members (queues, arrays)",
        ],
        "forbidden": [
            "TLM connect() calls",
            "raise/drop objection",
            "clocking block / interface access",
            "sequence start",
        ],
        "cross_ref": "base/uvm_component.svh; uvm_users_guide_1_2#build_phase",
    }),
    ("connect_phase", {
        "type": "function", "direction": "bottom-up", "time_cost": "zero",
        "actions": [
            "TLM port.connect(export) / analysis_port.connect(subscriber)",
            "seq_item_port.connect() between sequencer and driver",
            "config_db::set for TLM handles if children need them later",
        ],
        "forbidden": [
            "create() new components (use build_phase)",
            "config_db::get for vif (use build_phase)",
            "start sequences",
        ],
        "cross_ref": "base/uvm_port_base.svh; uvm_users_guide_1_2#connect_phase",
    }),
    ("end_of_elaboration_phase", {
        "type": "function", "direction": "bottom-up", "time_cost": "zero",
        "actions": [
            "print topology / report_phase summary",
            "close factory (no more overrides)",
            "verify config_db::exists for critical fields",
        ],
    }),
    ("start_of_simulation_phase", {
        "type": "function", "direction": "bottom-up", "time_cost": "zero",
        "actions": [
            "final configuration check",
            "open log files / trace files",
            "set component verbosity if runtime-configurable",
        ],
    }),
    ("run_phase", {
        "type": "task", "direction": "parallel (all components)", "time_cost": "simulation",
        "actions": [
            "sequence start (from test only, not from env)",
            "driver get_next_item / drive / item_done loop",
            "monitor collect transactions via analysis_port",
            "scoreboard analysis_imp receives and checks",
            "raise/drop objection (test-level: raise before seq, drop after drain)",
        ],
        "forbidden": [
            "create() or connect()",
            "config_db::set in children after build",
        ],
    }),
    ("extract_phase", {
        "type": "function", "direction": "bottom-up",
        "actions": ["collect final counters / scores from sub-components"],
    }),
    ("check_phase", {
        "type": "function", "direction": "bottom-up",
        "actions": ["assert final scoreboard has no mismatches / no DUT errors"],
    }),
    ("report_phase", {
        "type": "function", "direction": "bottom-up",
        "actions": ["print PASS/FAIL summary; set uvm_report_server exit count"],
    }),
])

# ---------------------------------------------------------------------------
# Component patterns
# ---------------------------------------------------------------------------
COMPONENT_PATTERNS = OrderedDict()

COMPONENT_PATTERNS["driver"] = {
    "decision": "Use uvm_driver#(REQ,RSP) when this component must *drive* stimulus "
                "onto a DUT interface.  It receives uvm_sequence_item objects from "
                "a sequencer via seq_item_port and translates them to pin-level "
                "activity.  For purely passive observation use uvm_monitor instead.",
    "extends": "uvm_driver #(REQ, RSP)",
    "phases": {
        "build_phase": ["vif = cfg.vif (from config_db)", "create sequencer port"],
        "connect_phase": ["(nothing — seq_item_port is auto-connected by agent)"],
        "run_phase": [
            "forever begin",
            "  seq_item_port.get_next_item(req);",
            "  drive_signals(req);",
            "  seq_item_port.item_done();",
            "end",
        ],
    },
    "code_skel": """\
class my_driver extends uvm_driver #(my_txn);
  `uvm_component_utils(my_driver)
  virtual my_if vif;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (!uvm_config_db#(virtual my_if)::get(this, "", "vif", vif))
      `uvm_fatal("DRV", "vif not set")
  endfunction

  task run_phase(uvm_phase phase);
    my_txn req;
    forever begin
      seq_item_port.get_next_item(req);
      drive(req);
      seq_item_port.item_done();
    end
  endtask

  extern task drive(my_txn t);
endclass
""",
    "connects": [
        "seq_item_port ← uvm_sequencer#(REQ,RSP)::seq_item_export (in agent::connect_phase)",
    ],
    "handshake": [
        "seq.get_next_item(req)  — driver side",
        "seq.item_done()         — driver side (RSP optional via item_done(rsp))",
        "seq.start_item(item)    — sequence side",
        "seq.finish_item(item)   — sequence side",
        "seq.get_response(rsp)   — sequence side (only if driver uses put_response)",
    ],
    "pitfalls": [
        "Forgetting `item_done()` → sequencer blocks forever → objection hang",
        "Using `get(response)` without driver `put_response()` → blocks",
        "Accessing vif in build_phase before config_db::get succeeds",
        "Clocking block races: always sample on @(vif.cb), never raw signals",
    ],
    "refs": {
        "source": "seq/uvm_driver.svh",
        "concept": "uvm_driver, sequence_sequencer_driver",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_driver",
    },
}

COMPONENT_PATTERNS["monitor"] = {
    "decision": "Use uvm_monitor for passive observation.  Never drives signals.  "
                "Collects transactions from the DUT interface and publishes them "
                "via uvm_analysis_port#(T).  The monitor must not know about "
                "scoreboard/coverage — it only broadcasts.",
    "extends": "uvm_monitor",
    "phases": {
        "build_phase": ["vif = cfg.vif (from config_db)", "create analysis_port"],
        "connect_phase": ["(subscribers connect here from env/agent)"],
        "run_phase": [
            "forever begin @(vif.cb);",
            "  if (transaction_valid) begin",
            "    collect_transaction(ap);",
            "  end",
            "end",
        ],
    },
    "code_skel": """\
class my_monitor extends uvm_monitor;
  `uvm_component_utils(my_monitor)
  virtual my_if vif;
  uvm_analysis_port #(my_txn) ap;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (!uvm_config_db#(virtual my_if)::get(this, "", "vif", vif))
      `uvm_fatal("MON", "vif not set")
  endfunction

  task run_phase(uvm_phase phase);
    forever begin
      @(vif.cb);
      if (vif.cb.valid && vif.cb.ready) begin
        my_txn t = my_txn::type_id::create("t");
        t.addr = vif.cb.addr;
        t.data = vif.cb.data;
        ap.write(t);
      end
    end
  endtask
endclass
""",
    "connects": [
        "analysis_port → uvm_agent::ap → env::scoreboard.analysis_export",
        "analysis_port → uvm_agent::ap → env::coverage_subscriber.analysis_export",
    ],
    "pitfalls": [
        "Using blocking transport in monitor → deadlocks scoreboard",
        "Putting scoreboard-specific checks in monitor → violates separation",
        "Not using clocking block → race condition between monitor and DUT",
    ],
    "refs": {
        "source": "comps/uvm_monitor.svh",
        "concept": "uvm_monitor, analysis_port",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_monitor",
    },
}

COMPONENT_PATTERNS["agent"] = {
    "decision": "Use uvm_agent as a container for driver + sequencer + monitor.  "
                "Set ``is_active`` via config_db to control whether the driver/sequencer "
                "are created (ACTIVE) or only the monitor (PASSIVE).",
    "extends": "uvm_agent",
    "phases": {
        "build_phase": [
            "get is_active from config_db",
            "create monitor (always)",
            "if (is_active == UVM_ACTIVE): create driver + sequencer",
        ],
        "connect_phase": [
            "driver.seq_item_port.connect(sequencer.seq_item_export)",
            "monitor.ap.connect(agent.ap)  // expose for env-level subscribers",
        ],
        "run_phase": ["(nothing — children handle this)"],
    },
    "code_skel": """\
class my_agent extends uvm_agent;
  `uvm_component_utils(my_agent)
  my_driver    drv;
  my_monitor   mon;
  uvm_sequencer #(my_txn) sqr;
  uvm_analysis_port #(my_txn) ap;
  uvm_active_passive_enum is_active;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    ap = new("ap", this);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (!uvm_config_db#(uvm_active_passive_enum)::get(this, "", "is_active", is_active))
      is_active = UVM_ACTIVE;
    mon = my_monitor::type_id::create("mon", this);
    if (is_active == UVM_ACTIVE) begin
      drv = my_driver::type_id::create("drv", this);
      sqr = uvm_sequencer#(my_txn)::type_id::create("sqr", this);
    end
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    mon.ap.connect(ap);
    if (is_active == UVM_ACTIVE)
      drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass
""",
    "connects": [
        "driver.seq_item_port ↔ sequencer.seq_item_export (in connect_phase)",
        "monitor.ap → agent.ap (expose upward)",
    ],
    "pitfalls": [
        "Connecting driver↔sequencer in build_phase → port not yet allocated",
        "Forgetting is_active guard → create passive driver → null vif crash",
        "Hard-coding interface name instead of using config_db::get",
    ],
    "refs": {
        "source": "comps/uvm_agent.svh",
        "concept": "uvm_agent",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_agent",
    },
}

COMPONENT_PATTERNS["scoreboard"] = {
    "decision": "Use uvm_scoreboard when you need transaction-level checking "
                "(data integrity, protocol compliance, ordering).  Subscribe to "
                "monitor analysis_ports via uvm_analysis_imp.  For simple "
                "coverage-only collection use uvm_subscriber instead.",
    "extends": "uvm_scoreboard",
    "phases": {
        "build_phase": ["create expected model queues / reference model"],
        "connect_phase": [
            "analysis_imp declarations with write() implementation",
            "(imp connections made by env, not scoreboard itself)",
        ],
        "run_phase": ["(nothing — write() is called asynchronously)"],
    },
    "code_skel": """\
class my_scoreboard extends uvm_scoreboard;
  `uvm_component_utils(my_scoreboard)
  uvm_analysis_imp #(my_txn, my_scoreboard) exp_imp;
  uvm_analysis_imp #(my_txn, my_scoreboard) act_imp;

  my_txn expected_queue[$];
  int mismatches = 0;

  function new(string name, uvm_component parent);
    super.new(name, parent);
    exp_imp = new("exp_imp", this);
    act_imp = new("act_imp", this);
  endfunction

  function void write_exp(my_txn t);
    expected_queue.push_back(t);
  endfunction

  function void write_act(my_txn t);
    if (expected_queue.size() == 0) begin
      `uvm_error("SB", $sformatf("unexpected txn addr=%h", t.addr))
      mismatches++;
    end else begin
      my_txn e = expected_queue.pop_front();
      if (!e.compare(t)) begin
        `uvm_error("SB", $sformatf("mismatch exp=%h act=%h", e.data, t.data))
        mismatches++;
      end
    end
  endfunction

  function void check_phase(uvm_phase phase);
    super.check_phase(phase);
    if (mismatches > 0)
      `uvm_error("SB", $sformatf("total mismatches=%0d", mismatches))
    if (expected_queue.size() > 0)
      `uvm_error("SB", $sformatf("%0d expected txns never observed", expected_queue.size()))
  endfunction
endclass
""",
    "connects": [
        "env: agent_mon_ap.connect(sb.exp_imp); ref_model_ap.connect(sb.act_imp)",
    ],
    "pitfalls": [
        "Forgetting check_phase final queue-empty assertion",
        "Using task instead of function for write() → analysis_imp requires function",
        "Not handling out-of-order transactions (use associative array keyed by tag)",
    ],
    "refs": {
        "source": "comps/uvm_scoreboard.svh",
        "concept": "uvm_scoreboard, analysis_imp",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_scoreboard",
    },
}

COMPONENT_PATTERNS["sequence"] = {
    "decision": "Use uvm_sequence#(REQ,RSP) to generate stimulus.  The sequence "
                "does NOT create components — it creates items via start_item/"
                "finish_item and optionally gets responses.  Configure via "
                "config_db or direct field assignment before start().",
    "extends": "uvm_sequence #(my_txn)",
    "phases": {
        "build_phase": ["(not a component — no build_phase)"],
        "run_phase": [
            "Called via seq.start(sequencer) from test's run_phase",
            "body() task: repeat(N) begin",
            "  `uvm_do(req)  or start_item(req); randomize(req); finish_item(req);",
            "end",
        ],
    },
    "code_skel": """\
class my_sequence extends uvm_sequence #(my_txn);
  `uvm_object_utils(my_sequence)
  int num_items = 10;

  function new(string name = "my_sequence");
    super.new(name);
  endfunction

  constraint c_num { num_items inside {[1:100]}; }

  task body();
    repeat (num_items) begin
      req = my_txn::type_id::create("req");
      start_item(req);
      if (!req.randomize() with { addr inside {[0:h 'FF]}; })
        `uvm_error("SEQ", "randomize failed")
      finish_item(req);
    end
  endtask
endclass
""",
    "connects": [
        "test.run_phase: my_sequence seq; seq.start(env.agent.sqr);",
    ],
    "pitfalls": [
        "Calling seq.start() outside run_phase → no simulation time for items",
        "Forgetting start_item/finish_item pair → transaction never sent",
        "Not checking randomize() return → silent constraint failures",
    ],
    "refs": {
        "source": "seq/uvm_sequence.svh, seq/uvm_sequence_base.svh",
        "concept": "uvm_sequence, start_item, finish_item",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_sequence",
    },
}

COMPONENT_PATTERNS["env"] = {
    "decision": "Use uvm_env as the top-level verification container.  Creates "
                "agents, scoreboards, coverage subscribers, register model.  "
                "Wires analysis ports between them in connect_phase.",
    "extends": "uvm_env",
    "phases": {
        "build_phase": [
            "create agents (active/passive via config_db)",
            "create scoreboard / coverage / ref_model",
            "set agent-level config (is_active, num_master, etc.)",
        ],
        "connect_phase": [
            "agent.ap.connect(scoreboard.exp_imp)",
            "agent.ap.connect(coverage.analysis_export)",
        ],
        "run_phase": ["(children handle this)"],
    },
    "code_skel": """\
class my_env extends uvm_env;
  `uvm_component_utils(my_env)
  my_agent       agt;
  my_scoreboard  sb;
  my_coverage    cov;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    agt = my_agent::type_id::create("agt", this);
    sb  = my_scoreboard::type_id::create("sb", this);
    cov = my_coverage::type_id::create("cov", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    agt.ap.connect(sb.exp_imp);
    agt.ap.connect(cov.analysis_export);
  endfunction
endclass
""",
    "connects": [
        "agent.ap → scoreboard.imp (in connect_phase)",
        "agent.ap → coverage.analysis_export (in connect_phase)",
    ],
    "pitfalls": [
        "Wiring connections in build_phase → TLM ports not yet constructed",
        "Not propagating is_active to sub-agents via config_db::set",
    ],
    "refs": {
        "source": "comps/uvm_env.svh",
        "concept": "uvm_env",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_env",
    },
}

COMPONENT_PATTERNS["test"] = {
    "decision": "Use uvm_test as the top-level entry.  Creates env, sets factory "
                "overrides, starts sequences in run_phase.  Raise objection "
                "before stimulus, drop after drain_time to flush in-flight items.",
    "extends": "uvm_test",
    "phases": {
        "build_phase": [
            "set factory overrides (before super.build_phase)",
            "create env",
            "set config_db for agents/sequences",
        ],
        "connect_phase": ["(env handles internal connections)"],
        "run_phase": [
            "raise_objection(this)",
            "seq.start(env.agt.sqr)",
            "#drain_time;  // flush in-flight transactions",
            "drop_objection(this)",
        ],
    },
    "code_skel": """\
class my_test extends uvm_test;
  `uvm_component_utils(my_test)
  my_env env;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    // Override BEFORE super.build_phase
    set_type_override_by_type(my_driver::get_type(), my_error_driver::get_type());
    super.build_phase(phase);
    env = my_env::type_id::create("env", this);
  endfunction

  task run_phase(uvm_phase phase);
    my_sequence seq = my_sequence::type_id::create("seq");
    phase.raise_objection(this, "starting stimulus");
    seq.num_items = 50;
    seq.start(env.agt.sqr);
    #100ns;  // drain time
    phase.drop_objection(this, "stimulus done");
  endtask
endclass
""",
    "connects": [
        "test creates env; test starts sequence on env's sequencer",
    ],
    "pitfalls": [
        "Factory override AFTER super.build_phase → children already created with old type",
        "No objection in run_phase → phase ends immediately, no stimulus runs",
        "No drain time after last item → driver still processing → lost transactions",
    ],
    "refs": {
        "source": "comps/uvm_test.svh",
        "concept": "uvm_test, factory override, objection",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_test",
    },
}

COMPONENT_PATTERNS["register_model"] = {
    "decision": "Use uvm_reg_block/uvm_reg/uvm_reg_field for register abstraction.  "
                "Wire an adapter (uvm_reg_adapter) to translate between reg operations "
                "and bus transactions.  Use a predictor (uvm_reg_predictor) to mirror "
                "DUT state back into the model.",
    "extends": "uvm_reg_block",
    "phases": {
        "build_phase": [
            "create reg fields/registers/blocks",
            "reg_block.build() / lock_model()",
        ],
        "connect_phase": [
            "reg_block.default_map.set_sequencer(sequencer, adapter)",
        ],
        "run_phase": [
            "reg_block.default_map.update() for mirror check",
            "reg_block.default_map.set_auto_predict(1) or explicit predictor",
        ],
    },
    "code_skel": """\
// Adapter
class my_reg_adapter extends uvm_reg_adapter;
  `uvm_object_utils(my_reg_adapter)

  function new(string name = "my_reg_adapter");
    super.new(name);
  endfunction

  function uvm_sequence_item reg2bus(const ref uvm_reg_bus_op rw);
    my_txn t = my_txn::type_id::create("t");
    t.addr  = rw.addr;
    t.data  = rw.data;
    t.write = (rw.kind == UVM_WRITE);
    return t;
  endfunction

  function void bus2reg(uvm_sequence_item bus_item, ref uvm_reg_bus_op rw);
    my_txn t;
    if (!$cast(t, bus_item)) return;
    rw.addr   = t.addr;
    rw.data   = t.data;
    rw.kind   = t.write ? UVM_WRITE : UVM_READ;
    rw.status = UVM_IS_OK;
  endfunction
endclass
""",
    "connects": [
        "reg_block.default_map.set_sequencer(agent.sqr, adapter)  // connect_phase",
        "reg_block.default_map.set_auto_predict(1)  // or wire predictor",
    ],
    "pitfalls": [
        "Forgetting lock_model() before map.set_sequencer → assertion",
        "Not setting adapter.regdata_width → bus2reg truncates data",
        "Using auto_predict with external writes → mirror diverges from DUT",
    ],
    "refs": {
        "source": "reg/uvm_reg_block.svh, reg/uvm_reg_adapter.svh",
        "concept": "uvm_reg_block, uvm_reg_adapter",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_reg_block",
    },
}

COMPONENT_PATTERNS["factory_override"] = {
    "decision": "Factory overrides allow substituting a component or object type "
                "without modifying the original testbench.  Use type override for "
                "global replacement; instance override for targeted replacement.  "
                "MUST be set before super.build_phase() in the test.",
    "extends": "(not a component — a mechanism)",
    "phases": {
        "build_phase": [
            "set_type_override_by_type(T::get_type(), SubT::get_type())",
            "set_inst_override_by_type(T::get_type(), SubT::get_type(), \"env.agent.*\")",
            "— must come BEFORE super.build_phase(phase) —",
        ],
    },
    "code_skel": """\
// Type override (global)
set_type_override_by_type(my_driver::get_type(), my_error_driver::get_type());

// Instance override (targeted path glob)
set_inst_override_by_type(
  my_driver::get_type(),
  my_error_driver::get_type(),
  "env.agt.drv"  // exact path
);
// or wildcard:
set_inst_override_by_type(
  my_driver::get_type(),
  my_error_driver::get_type(),
  "env.*.drv"   // all agents
);

// String override (for runtime +uvm_set_type_override)
// +uvm_set_type_override=my_driver,my_error_driver
""",
    "connects": [],
    "pitfalls": [
        "Override AFTER super.build_phase → too late, children already created",
        "Type not registered with factory (`uvm_component_utils missing) → silent fallback to base type",
        "Case-sensitive type name in string override → factory lookup fails",
        "Overriding an object type with a component type (or vice versa) → uvm_fatal",
    ],
    "refs": {
        "source": "base/uvm_factory.svh, base/uvm_registry.svh",
        "concept": "uvm_factory, factory_override",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_factory",
    },
}

COMPONENT_PATTERNS["objection_lifecycle"] = {
    "decision": "Objections coordinate phase completion across all components.  "
                "Raise before time-consuming activity, drop when done.  Drain time "
                "gives in-flight transactions time to complete after the last drop.",
    "extends": "(not a component — a mechanism)",
    "phases": {
        "run_phase": [
            "phase.raise_objection(this, \"reason\");",
            "  // stimulus / sequence start / drive activity",
            "  #(drain_time);  // e.g. #100ns",
            "phase.drop_objection(this, \"done\");",
        ],
    },
    "code_skel": """\
task run_phase(uvm_phase phase);
  phase.raise_objection(this, "starting");
  begin
    my_seq seq = my_seq::type_id::create("seq");
    seq.start(env.agt.sqr);
  end
  // Drain: let driver finish last item
  #200ns;
  phase.drop_objection(this, "done");
endtask
""",
    "connects": [],
    "pitfalls": [
        "No objection in run_phase → phase ends at t=0, nothing runs",
        "Raise/drop in both test and env → double-raise, phase hangs",
        "No drain time → driver mid-item when phase ends → lost transactions",
        "+UVM_OBJECTION_TRACE plusarg for debugging hanging objections",
    ],
    "refs": {
        "source": "base/uvm_objection.svh",
        "concept": "uvm_objection, phase objection, drain_time",
        "manual": "UVM_Class_Reference_Manual_1_2 §uvm_objection",
    },
}

COMPONENT_PATTERNS["tlm_connection"] = {
    "decision": "TLM (Transaction-Level Modeling) ports define how components exchange "
                "transactions.  Use analysis_port/subscriber for broadcast "
                "(monitor→scoreboard), blocking transport for request-response "
                "(driver↔sequencer via seq_item_port).",
    "extends": "(not a component — a mechanism)",
    "phases": {
        "connect_phase": [
            "port.connect(export);",
            "analysis_port.connect(analysis_imp);",
            "seq_item_port.connect(seq_item_export);",
        ],
    },
    "code_skel": """\
// Analysis port broadcast (one → many)
class my_env extends uvm_env;
  my_monitor mon;
  my_sb sb;
  my_cov cov;

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    mon.ap.connect(sb.item_imp);     // scoreboard gets every txn
    mon.ap.connect(cov.analysis_export); // coverage gets every txn
  endfunction
endclass

// Sequence item handshake (one ↔ one)
class my_agent extends uvm_agent;
  my_driver drv;
  my_sequencer sqr;

  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    drv.seq_item_port.connect(sqr.seq_item_export);
  endfunction
endclass
""",
    "connects": [],
    "pitfalls": [
        "connect() in build_phase → peer ports not yet created",
        "Multiple analysis_imp in same subscriber without unique write_N names",
        "Forgetting to call parent's connect_phase → missed inherited connections",
    ],
    "refs": {
        "source": "tlm1/uvm_port_base.svh, tlm1/uvm_analysis_port.svh",
        "concept": "analysis_port, tlm_connection, seq_item_port",
        "manual": "UVM_Class_Reference_Manual_1_2 §TLM",
    },
}

# ---------------------------------------------------------------------------
# Methodology checklist by verification level
# ---------------------------------------------------------------------------
CHECKLISTS = OrderedDict([
    ("block_level", [
        "Agent(s) with driver+monitor+sequencer (active) and monitor-only (passive)",
        "Scoreboard with expected vs actual transaction checking",
        "Functional coverage subscriber (covergroup inside uvm_subscriber)",
        "Register model with adapter + auto-predict",
        "At least one constrained-random sequence + one directed error sequence",
        "Factory override for error injection variant of driver",
        "Objection raise/drop with drain time in test run_phase",
        "config_db for vif, is_active, num_lanes — no hard-coded paths",
        "check_phase: scoreboard mismatch count == 0 AND expected_queue empty",
        "report_phase: `uvm_info PASS/FAIL summary",
    ]),
    ("subsystem_level", [
        "Multiple agents (master + slave, or DUT + reference model)",
        "Scoreboard with ordering / protocol compliance checking",
        "Cross-agent coverage (interaction scenarios)",
        "Register model covering all address map / alias registers",
        "Interrupt / event sequence integration",
        "Reset sequence integration (pre_reset / reset / post_reset phases)",
        "Low-power sequence integration (if UPF-aware)",
    ]),
    ("soc_level", [
        "Passive-only monitoring of all sub-block interfaces",
        "Virtual sequencer coordinating multiple sub-block sequences",
        "System-level scoreboard (through traffic, not per-block)",
        "Speed adaptation / clock domain crossing checking",
        "Boot / shutdown / reset regression",
        "Performance counters / QoS monitoring",
    ]),
])

# ---------------------------------------------------------------------------
# Decision trees (intent keywords → recommended pattern + rationale)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tool-chain recommendations (agent workflow orchestration)
# ---------------------------------------------------------------------------
_WORKFLOW_CHAINS = {
    "driver": [
        "chip_uvm_methodology(op=pattern,pattern=driver)",
        "chip_uvm_method_source(class=uvm_driver)",
        "chip_generate_testbench",
        "chip_check_uvm_compliance",
        "chip_run_simulation",
    ],
    "monitor": [
        "chip_uvm_methodology(op=pattern,pattern=monitor)",
        "chip_uvm_method_source(class=uvm_monitor)",
        "chip_generate_testbench",
        "chip_check_uvm_compliance",
    ],
    "agent": [
        "chip_uvm_methodology(op=pattern,pattern=agent)",
        "chip_generate_testbench",
        "chip_check_uvm_compliance",
    ],
    "scoreboard": [
        "chip_uvm_methodology(op=pattern,pattern=scoreboard)",
        "chip_uvm_method_source(class=uvm_scoreboard)",
        "chip_generate_testbench",
        "chip_check_uvm_compliance",
    ],
    "sequence": [
        "chip_uvm_methodology(op=pattern,pattern=sequence)",
        "chip_uvm_method_source(class=uvm_sequence)",
        "chip_generate_testbench",
    ],
    "env": [
        "chip_uvm_methodology(op=pattern,pattern=env)",
        "chip_generate_testbench",
        "chip_check_uvm_compliance",
        "chip_run_simulation",
    ],
    "register_model": [
        "chip_uvm_methodology(op=pattern,pattern=register_model)",
        "chip_uvm_method_source(class=uvm_reg_block)",
        "chip_generate_testbench",
    ],
    "test": [
        "chip_uvm_methodology(op=pattern,pattern=test)",
        "chip_generate_testbench",
        "chip_check_uvm_compliance",
        "chip_run_simulation",
    ],
    "factory_override": [
        "chip_uvm_methodology(op=pattern,pattern=factory_override)",
        "chip_uvm_method_source(class=uvm_factory)",
        "chip_check_uvm_compliance",
    ],
    "objection_lifecycle": [
        "chip_uvm_methodology(op=pattern,pattern=objection_lifecycle)",
        "chip_uvm_method_source(class=uvm_objection)",
        "chip_run_simulation",
    ],
    "tlm_connection": [
        "chip_uvm_methodology(op=pattern,pattern=tlm_connection)",
        "chip_uvm_method_source(class=uvm_port_base)",
        "chip_check_uvm_compliance",
    ],
}

_DECISION_RULES = [
    {
        "keywords": ["drive", "stimulus", "driver", "激励", "驱动"],
        "pattern": "driver",
        "rationale": "Intent involves actively generating pin-level or transaction-level stimulus onto the DUT.",
    },
    {
        "keywords": ["monitor", "observe", "capture", "监听", "观测"],
        "pattern": "monitor",
        "rationale": "Intent involves passive observation and broadcasting via analysis_port.",
    },
    {
        "keywords": ["agent", "container", "proxy", "代理"],
        "pattern": "agent",
        "rationale": "Intent involves grouping driver+sequencer+monitor as a reusable IP block.",
    },
    {
        "keywords": ["scoreboard", "checker", "compare", "check", "记分板", "校验"],
        "pattern": "scoreboard",
        "rationale": "Intent involves transaction-level expected-vs-actual comparison.",
    },
    {
        "keywords": ["sequence", "stimulus generation", "randomize", "约束", "随机"],
        "pattern": "sequence",
        "rationale": "Intent involves generating constrained-random or directed transaction streams.",
    },
    {
        "keywords": ["env", "environment", "top-level", "环境"],
        "pattern": "env",
        "rationale": "Intent involves assembling the verification hierarchy and wiring analysis connections.",
    },
    {
        "keywords": ["test", "scenario", "override", "override type", "用例"],
        "pattern": "test",
        "rationale": "Intent involves the top-level test that configures the env and starts sequences.",
    },
    {
        "keywords": ["register", "reg_model", "ral", "adapter", "predictor", "寄存器"],
        "pattern": "register_model",
        "rationale": "Intent involves register abstraction, backdoor/frontdoor access, or mirror checking.",
    },
    {
        "keywords": ["factory", "override", "replace type", "类型替换"],
        "pattern": "factory_override",
        "rationale": "Intent involves runtime type substitution without modifying original code.",
    },
    {
        "keywords": ["objection", "hang", "drain", "phase end", "挂起"],
        "pattern": "objection_lifecycle",
        "rationale": "Intent involves phase completion coordination or debugging hanging simulations.",
    },
    {
        "keywords": ["tlm", "port", "export", "analysis", "connect", "连接"],
        "pattern": "tlm_connection",
        "rationale": "Intent involves wiring TLM connections between components.",
    },
    {
        "keywords": ["build_phase", "connect_phase", "run_phase", "phase", "阶段"],
        "pattern": "__phase_map__",
        "rationale": "Intent involves understanding what actions belong in which UVM phase.",
    },
    {
        "keywords": ["checklist", "signoff", "coverage closure", "验证清单"],
        "pattern": "__checklist__",
        "rationale": "Intent involves a verification-level methodology checklist.",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_phase_map() -> dict:
    """Full phase decision map."""
    return {"phases": {k: dict(v) for k, v in PHASE_MAP.items()}}


def get_pattern(pattern_name: str) -> dict:
    """Get a specific component pattern by name."""
    if pattern_name not in COMPONENT_PATTERNS:
        return {"error": f"unknown pattern: {pattern_name}",
                "available": list(COMPONENT_PATTERNS.keys())}
    p = dict(COMPONENT_PATTERNS[pattern_name])
    p["pattern"] = pattern_name
    p["next_tools"] = _WORKFLOW_CHAINS.get(pattern_name, [])
    return p


def list_patterns() -> list[str]:
    return list(COMPONENT_PATTERNS.keys())


def get_checklist(level: str) -> dict:
    if level not in CHECKLISTS:
        return {"error": f"unknown level: {level}", "available": list(CHECKLISTS.keys())}
    return {"level": level, "items": CHECKLISTS[level]}


def match_intent(query: str) -> list[dict]:
    """Match an intent string to relevant methodology patterns, ranked."""
    q = query.lower()
    matches = []
    for rule in _DECISION_RULES:
        hits = sum(1 for kw in rule["keywords"] if kw in q)
        if hits > 0:
            entry = {
                "pattern": rule["pattern"],
                "score": hits,
                "rationale": rule["rationale"],
            }
            if rule["pattern"] == "__phase_map__":
                entry["data"] = get_phase_map()
            elif rule["pattern"] == "__checklist__":
                entry["data"] = {lvl: CHECKLISTS[lvl] for lvl in CHECKLISTS}
            else:
                entry["data"] = get_pattern(rule["pattern"])
            matches.append(entry)
    matches.sort(key=lambda x: -x["score"])
    return matches


def decide(query: str) -> dict:
    """Top-level decision: given an intent, return the best pattern + alternatives."""
    matches = match_intent(query)
    if not matches:
        return {
            "query": query,
            "matched": False,
            "message": "No specific UVM methodology pattern matched. "
                       "Use chip_uvm_semantic or chip_uvm_explain for concept-level Q&A.",
            "available_patterns": list(COMPONENT_PATTERNS.keys()),
        }
    return {
        "query": query,
        "matched": True,
        "best_pattern": matches[0]["pattern"],
        "best_rationale": matches[0]["rationale"],
        "best_data": matches[0]["data"],
        "alternatives": [
            {"pattern": m["pattern"], "score": m["score"],
             "rationale": m["rationale"]}
            for m in matches[1:3]
        ],
    }


def get_all_pitfalls() -> list[dict]:
    """Aggregate all pitfalls from every pattern."""
    out = []
    for name, p in COMPONENT_PATTERNS.items():
        for pit in p.get("pitfalls", []):
            out.append({"pattern": name, "pitfall": pit})
    return out


def methodology_checklist_for_intent(query: str) -> dict:
    """Given an intent, return both the best pattern AND the appropriate checklist."""
    decision = decide(query)
    if not decision.get("matched"):
        return decision
    level = "block_level"  # default
    ql = query.lower()
    if any(w in ql for w in ["soc", "system", "chip-level", "top", "整机"]):
        level = "soc_level"
    elif any(w in ql for w in ["subsystem", "cluster", "sub-block", "子系统"]):
        level = "subsystem_level"
    cl = get_checklist(level)
    return {
        "matched": True,
        "query": query,
        "best_pattern": decision["best_pattern"],
        "best_rationale": decision["best_rationale"],
        "pattern_data": decision["best_data"],
        "checklist_level": level,
        "checklist": cl["items"],
        "alternatives": decision.get("alternatives", []),
    }
