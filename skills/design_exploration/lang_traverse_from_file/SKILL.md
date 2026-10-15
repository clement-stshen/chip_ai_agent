---
name: lang_traverse_from_file
target: [design_exploration]
description: |
  Traverse hierarchy from scope file to leaf using hier_tree_trv.
  Reads instance paths from SCOPE_FILE_PATH and traverses each to leaf.
match_conditions:
  scope_mode: ["full_traverse", "def_recursive", "inst_recursive"]
---

## When to Use
- Scope file (SCOPE_FILE_PATH) contains instance paths to traverse
- User asks to traverse "to leaf" or "recursively" from given scopes
- Search needs to go deep into hierarchy from pre-located scopes

## Pre-located Scopes
- `SCOPE_FILE_PATH` contains instance paths (one per line)
- `OUTPUT_JSON_PATH` is where results should be written
- Each line is a starting point for hier_tree_trv traversal

## Key APIs
- `lang.handle_by_name(scope_path, None)` - Get scope handle
- `lang.hier_tree_trv_register_cb(npi_type, callback, cb_data)` - Register callback for object type
- `lang.hier_tree_trv(scope_name)` - Start traversal from scope
- `lang.hier_tree_trv_reset_cb()` - Reset callbacks after use

## NPI Types for Signals
```python
SIGNAL_TYPES = ["npiReg", "npiNet", "npiArrayVar", "npiArrayNet", "npiVariable"]
```

## Steps

### Step 1: Read scopes and define callback
```python
import json
from pynpi import lang

with open(SCOPE_FILE_PATH, "r") as f:
    scope_paths = [line.strip() for line in f if line.strip()]

results = []

def collect_signal(hdl, userdata):
    full_name = hdl.full_name()
    if full_name:
        userdata.append({
            "identifier": full_name,
            "attributes": {"type": hdl.type()}
        })
```

### Step 2: Register callbacks and traverse each scope
```python
SIGNAL_TYPES = ["npiReg", "npiNet", "npiArrayVar", "npiArrayNet", "npiVariable"]

for npi_type in SIGNAL_TYPES:
    lang.hier_tree_trv_register_cb(npi_type, collect_signal, results)

for scope_path in scope_paths:
    scope_hdl = lang.handle_by_name(scope_path, None)
    if scope_hdl:
        lang.hier_tree_trv(scope_hdl.full_name())

lang.hier_tree_trv_reset_cb()
```

### Step 3: Write JSON output
```python
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## Complete Example
```python
import json
from pynpi import lang

# Read scope file
with open(SCOPE_FILE_PATH, "r") as f:
    scope_paths = [line.strip() for line in f if line.strip()]

results = []

def collect_signal(hdl, userdata):
    full_name = hdl.full_name()
    if full_name:
        userdata.append({
            "identifier": full_name,
            "attributes": {"type": hdl.type()}
        })

# Register for all signal types
SIGNAL_TYPES = ["npiReg", "npiNet", "npiArrayVar", "npiArrayNet", "npiVariable"]
for npi_type in SIGNAL_TYPES:
    lang.hier_tree_trv_register_cb(npi_type, collect_signal, results)

# Traverse each scope to leaf
for scope_path in scope_paths:
    scope_hdl = lang.handle_by_name(scope_path, None)
    if scope_hdl:
        lang.hier_tree_trv(scope_hdl.full_name())

lang.hier_tree_trv_reset_cb()

# Write output
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## IMPORTANT
- Always call `hier_tree_trv_reset_cb()` after traversal
- Register callbacks BEFORE calling `hier_tree_trv`
- hier_tree_trv traverses ALL descendants (to leaf) by default
- Use `handle_by_name` to get scope handle before traversal
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
