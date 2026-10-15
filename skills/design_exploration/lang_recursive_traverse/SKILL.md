---
name: lang_recursive_traverse
target: [design_exploration]
description: |
  Recursively traverse from a root definition to find all reachable module definitions.
  Uses BFS over child definitions to discover the complete module hierarchy.
match_conditions:
  scope_mode: ["def_recursive"]
---

## When to Use
- User asks for "all modules under X"
- User asks for "complete hierarchy starting from X"
- User asks for "all reachable modules from X"
- User wants to explore the full module tree recursively

## Key Concept: BFS Over Definitions
- Start from a root definition
- Find all child definitions (modules instantiated within)
- For each child, find its children, and so on
- Use a visited set to avoid cycles
- Result is the complete set of reachable definitions

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

### Step 1: Define helper to get child definitions
```python
from pynpi import lang

INSTANCE_TYPES = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]

def get_child_definitions(def_name):
    '''Get definitions of direct child instances.'''
    instances = lang.find_inst_with_def_wildcard(None, [def_name])
    child_defs = set()
    if instances:
        inst = instances[0]
        for child in inst.internal_scope_handles():
            if child.type() in INSTANCE_TYPES:
                child_def = child.def_name()
                if child_def:
                    child_defs.add(child_def)
    return child_defs
```

### Step 2: BFS to find all reachable definitions
```python
root_def = "YOUR_ROOT_MODULE"  # Replace with actual root module

visited = set()
to_visit = [root_def]

while to_visit:
    current = to_visit.pop(0)  # BFS: pop from front
    if current in visited:
        continue
    visited.add(current)

    children = get_child_definitions(current)
    for child in children:
        if child not in visited:
            to_visit.append(child)
```

### Step 3: Write JSON output
```python
import json
results = [
    {"identifier": def_name, "attributes": {"type": "definition"}}
    for def_name in sorted(visited)
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

INSTANCE_TYPES = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]

def get_child_definitions(def_name):
    instances = lang.find_inst_with_def_wildcard(None, [def_name])
    child_defs = set()
    if instances:
        inst = instances[0]
        for child in inst.internal_scope_handles():
            if child.type() in INSTANCE_TYPES:
                child_def = child.def_name()
                if child_def:
                    child_defs.add(child_def)
    return child_defs

# BFS from root
root_def = "top"
visited = set()
to_visit = [root_def]

while to_visit:
    current = to_visit.pop(0)
    if current in visited:
        continue
    visited.add(current)
    children = get_child_definitions(current)
    for child in children:
        if child not in visited:
            to_visit.append(child)

results = [
    {"identifier": d, "attributes": {"type": "definition"}}
    for d in sorted(visited)
]
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## Notes on Performance
- This approach makes one `find_inst_with_def_wildcard` call per unique definition
- For large designs, consider using SDB APIs for better performance
- The visited set prevents infinite loops from cyclic instantiation

## IMPORTANT
- Always use a visited set to prevent infinite loops
- Use BFS (pop from front) to get breadth-first order
- Each definition appears exactly once in the result
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
