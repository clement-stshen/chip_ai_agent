---
name: netlist_traverse_hierarchy
target: [design_exploration]
description: |
  Netlist hierarchy traversal for counting/listing/finding many objects.
  Use netlist.hier_tree_trv with registered callbacks.
match_conditions:
  traverse_mode: ["traverse"]
---

## When to Use
User requests involve counting, listing, or finding many objects across the design:
- "List all flip-flops"
- "Count instances with FSM"
- "Find all latches without reset"

## Key APIs
- `netlist.hier_tree_trv_register_cb(obj_type, callback, cb_data)` - Register callback
- `netlist.hier_tree_trv(scope_hier_name=None)` - Traverse (None = whole design)
- `netlist.hier_tree_trv_reset_cb()` - Reset callbacks

## Object Types
- `ObjectType.INST` - Instances
- `ObjectType.PORT` - Ports
- `ObjectType.INSTPORT` - Instance ports
- `ObjectType.DECL_NET` - Declared nets
- `ObjectType.SLICE_NET` - Slice nets
- `ObjectType.CONCAT_NET` - Concatenation nets

## Steps

### Step 1: Define callback
```python
collected = []
def cb(hdl, cb_data):
    # Filter by cell_type if needed
    if hdl.cell_type() == target_cell_type:
        cb_data.append(hdl.full_name())
```

### Step 2: Register callback
```python
netlist.hier_tree_trv_register_cb(ObjectType.INST, cb, collected)
```

### Step 3: Traverse
```python
# From specific scope:
netlist.hier_tree_trv(scope_hier_name="top.module1")
# Or whole design:
netlist.hier_tree_trv(scope_hier_name=None)
```

### Step 4: Cleanup
```python
netlist.hier_tree_trv_reset_cb()
```

## CRITICAL RULES

### 1. None Checking (VERY IMPORTANT)
Handle member functions with handle return types return `None` if the object doesn't exist.
You MUST check for None before using the returned value:
```python
# WRONG - will crash if connected_net returns None
net = pin.connected_net()
print(net.full_name())  # Error if net is None!

# CORRECT
net = pin.connected_net()
if net is not None:
    print(net.full_name())
```

### 2. No Unsupported Functions
Do NOT use any function or command that is NOT in the provided documentation.
Calling unsupported functions will lead to execution errors.

### 3. Wildcards in Traversal
When user provides patterns (e.g., `*`, prefixes, partial names):
- Traverse the relevant scope
- Filter by `hdl.full_name()` or `hdl.name()` in the callback
```python
def cb(hdl, cb_data):
    if "pattern" in hdl.name():  # or use fnmatch
        cb_data.append(hdl.full_name())
```
