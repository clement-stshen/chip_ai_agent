---
name: netlist_class_types
target: [design_exploration]
description: |
  Cell type filters for Netlist queries. Includes FSM control signal queries.
match_conditions:
  cell_type_filter: ["flip-flop", "latch", "mux", "fsm", "tri-state", "register", "control signal"]
---

## IMPORTANT: FSM Control Signals

When user asks for "control signals" that affect FSM state transitions, you MUST use this pattern:

```python
# Find FSM cells and get their control signals via npiNlFSMControlPort
for child in inst.inst_list():
    if child.cell_type() == "npiNlFSMCell":
        for pin in child.instport_list():
            if pin.port_type() == "npiNlFSMControlPort":
                control_net = pin.connected_net()
                # control_net is the signal that affects FSM transitions
```

DO NOT search by name pattern like `"control" in name`. Use `npiNlFSMControlPort` port type.

## Cell Type Mapping

Use `hdl.cell_type()` to filter instances by cell type.

### Hardware Term → cell_type() Values

| Hardware Term | cell_type() Values |
|--------------|-------------------|
| not/inverter | npiNlNotCell |
| and | npiNlAndCell |
| or | npiNlOrCell |
| xor | npiNlXorCell |
| adder | npiNlAdderCell |
| equal compare | npiNlEqCompCell |
| shift left | npiNlShiftLeftCell |
| shift right | npiNlShiftRightCell |
| mux/multiplexer | npiNlMuxCell |
| assign | npiNlAssignCell |
| flip-flop | npiNlFlipFlopCell |
| tri-state buffer | npiNlTriBufCell, npiNlTriCell |
| latch | npiNlLatchCell, npiNlInfLatchCell, npiNlLatchComboCell |
| FSM | npiNlFSMCell |
| module instance | npiNlModuleCell |

### Register (all register types) — CRITICAL: Must check ALL of these:
When user asks for "registers", you MUST filter by ALL of the following cell types.
Do NOT only check npiNlFlipFlopCell — latches and other storage elements are also registers.

- npiNlFlipFlopCell (flip-flops)
- npiNlLatchCell (latches)
- npiNlExternalRamCell (external RAM)
- npiNlFSMCell (FSM cells)
- npiNlInfLatchCell (inferred latches)
- npiNlFlipFlopComboCell (flip-flop with combo logic)
- npiNlLatchComboCell (latch with combo logic)

```python
# CORRECT pattern for finding all registers:
REGISTER_TYPES = {
    "npiNlFlipFlopCell", "npiNlLatchCell", "npiNlExternalRamCell",
    "npiNlFSMCell", "npiNlInfLatchCell", "npiNlFlipFlopComboCell",
    "npiNlLatchComboCell"
}

for child in inst.inst_list():
    if child.cell_type() in REGISTER_TYPES:
        # This is a register
```

## Special Port Types

For behavior-specific queries, combine cell_type() with port_type():

### Flip-flop reset default value:
```python
if inst.cell_type() == "npiNlFlipFlopCell":
    for pin in inst.instport_list():
        if pin.port_type() == "npiNlRegisteredPort":
            reset_value = pin.reset_default_value()  # None if missing
```
