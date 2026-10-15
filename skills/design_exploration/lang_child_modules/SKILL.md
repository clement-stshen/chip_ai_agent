---
name: lang_child_modules
target: [design_exploration]
description: |
  Find direct child module definitions of a module.
  Use internal_scope_handles() and filter for instance types, then get their def_name().
match_conditions:
  class_types: ["child", "submodule", "instance"]
  scope_mode: ["def_scope"]
---

## When to Use
- User asks "what modules are instantiated in X"
- User asks for "child modules of X"
- User asks for "submodules" or "instances within module"

## Key Concept
- Get a representative instance of the parent module
- Use internal_scope_handles() to find child scopes
- Filter for instance types (npiModule, npiInterface, npiPackage, npiProgram)
- Extract their def_name() to get the definition names

## Key APIs
- `lang.find_inst_with_def_wildcard(None, [def_name])` - Find instances of a definition
- `instance.internal_scope_handles()` - Get child scopes
- `child.type()` - Check if it's an instance type
- `child.def_name()` - Get the definition name of an instance

## Instance Types
```python
INSTANCE_TYPES = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]
```

## Steps

### Step 1: Get a representative instance
```python
from pynpi import lang

def_name = "YOUR_MODULE_NAME"  # Replace with actual module name
instances = lang.find_inst_with_def_wildcard(None, [def_name])
if not instances:
    # No instances found
    result = {"total_count": 0, "objects": []}
else:
    inst = instances[0]  # Use first instance as representative
```

### Step 2: Find child definitions
```python
INSTANCE_TYPES = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]
child_defs = set()

for child in inst.internal_scope_handles():
    if child.type() in INSTANCE_TYPES:
        child_def = child.def_name()
        if child_def:
            child_defs.add(child_def)
```

### Step 3: Write JSON output
```python
import json
results = [
    {"identifier": def_name, "attributes": {"type": "definition"}}
    for def_name in sorted(child_defs)
]
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## Example Code
```python
from pynpi import lang
import json

parent_def = "cpu"
instances = lang.find_inst_with_def_wildcard(None, [parent_def])

INSTANCE_TYPES = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]
child_defs = set()

if instances:
    inst = instances[0]
    for child in inst.internal_scope_handles():
        if child.type() in INSTANCE_TYPES:
            child_def = child.def_name()
            if child_def:
                child_defs.add(child_def)

results = [
    {"identifier": d, "attributes": {"type": "definition"}}
    for d in sorted(child_defs)
]
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## IMPORTANT
- Only consider instance types: npiModule, npiInterface, npiPackage, npiProgram
- Use def_name() to get the definition name, not name() which gives instance name
- Use a set to avoid duplicates when same module is instantiated multiple times
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
