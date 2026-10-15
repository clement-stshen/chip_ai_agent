---
name: netlist_scope_based_access
target: [design_exploration]
description: |
  Scope-based access to Netlist objects using inst_list, port_list, net_list.
  For searching within pre-located scopes without recursive traversal.
match_conditions:
  scope_mode: ["scope_based"]
---

## When to Use
User requests to find objects "in" or "within" a specific scope WITHOUT recursive keywords:
- "Find flip-flops in top.dut"
- "List latches in module sub"
- "Unconnected ports in scope X"

## Key APIs
- `inst = netlist.get_inst(scope_name)` - Get instance handle by full path
- `inst.inst_list()` - Get direct child instances (includes inferred cells)
- `inst.port_list()` - Get ports of the instance
- `inst.net_list()` - Get nets within the instance

## Pattern: Single-Level Cell Type Search

```python
from pynpi import netlist
import json

# Read scopes from file
with open(SCOPE_FILE_PATH, "r") as f:
    scope_list = [line.strip() for line in f if line.strip()]

result = {"total_count": 0, "objects": []}

for scope_name in scope_list:
    inst = netlist.get_inst(scope_name)
    if inst is None:
        continue

    # Search direct children
    for child in inst.inst_list():
        cell_type = child.cell_type()
        if cell_type == "TARGET_CELL_TYPE":  # e.g., "npiNlFlipFlopCell"
            result["objects"].append({
                "identifier": child.full_name(),
                "attributes": {"cell_type": cell_type}
            })

result["total_count"] = len(result["objects"])
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(result, f, indent=2)
```

## Pattern: Single-Level Port Search

```python
for scope_name in scope_list:
    inst = netlist.get_inst(scope_name)
    if inst is None:
        continue

    for port in inst.port_list():
        # Check port properties
        connected = port.connected_pin()
        if connected is None:  # Unconnected port
            result["objects"].append({
                "identifier": port.full_name(),
                "attributes": {"connected": False}
            })
```

## CRITICAL RULES

### 1. Always Check for None
```python
inst = netlist.get_inst(scope_name)
if inst is None:
    continue  # Skip if scope not found
```

### 2. Cell Types for Filtering
Common cell_type() values for inferred cells:
- `npiNlFlipFlopCell` - Flip-flops
- `npiNlLatchCell`, `npiNlInfLatchCell` - Latches
- `npiNlMuxCell` - Multiplexers
- `npiNlFSMCell` - FSM
