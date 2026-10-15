---
name: netlist_traverse_from_file
target: [design_exploration]
description: |
  Read scope list from SCOPE_FILE_PATH and iterate over each scope.
  Essential for staged flow integration with Netlist.
match_conditions:
  staged_flow: true
---

## When to Use
When the prompt mentions "Scope file:" and provides SCOPE_FILE_PATH:
- Staged flow pre-locates module instances
- Code generation reads from the scope file
- Iterate over each scope to search for objects

## REQUIRED Pattern

When you see "Scope file:" and "Output file:" in the prompt:

```python
import json
from pynpi import netlist

# CRITICAL: Copy exact paths from the prompt
SCOPE_FILE_PATH = "/path/from/prompt"  # COPY exact path
OUTPUT_JSON_PATH = "/path/from/prompt"  # COPY exact path

# Read scope list from file
with open(SCOPE_FILE_PATH, "r") as f:
    scope_list = [line.strip() for line in f if line.strip()]

result = {"total_count": 0, "objects": []}

for scope_name in scope_list:
    inst = netlist.get_inst(scope_name)
    if inst is None:
        continue

    # For scope_based: use inst.inst_list(), inst.port_list()
    # For full_traverse: use netlist.hier_tree_trv(scope_name)

    # ... search logic ...

result["total_count"] = len(result["objects"])
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(result, f, indent=2)
print(f"Total: {result['total_count']}")
```

## Scope-Based vs Full-Traverse

### Scope-Based (default)
```python
for scope_name in scope_list:
    inst = netlist.get_inst(scope_name)
    if inst is None:
        continue
    for child in inst.inst_list():
        # Search direct children only
        if child.cell_type() == target_type:
            result["objects"].append(...)
```

### Full-Traverse (to leaf)
```python
def cb_func(hdl, cb_data):
    if hdl.cell_type() == target_type:
        cb_data.append({"identifier": hdl.full_name(), ...})

for scope_name in scope_list:
    netlist.hier_tree_trv_register_cb(netlist.ObjectType.INST, cb_func, result["objects"])
    netlist.hier_tree_trv(scope_name)
    netlist.hier_tree_trv_reset_cb()
```

## CRITICAL RULES

1. **ALWAYS define SCOPE_FILE_PATH and OUTPUT_JSON_PATH at the TOP of your code**
2. **COPY exact paths from the prompt** - do not modify them
3. **Always check for None** before using handles
4. **Reset callbacks** after hier_tree_trv if used
