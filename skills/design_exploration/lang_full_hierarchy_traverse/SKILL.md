---
name: lang_full_hierarchy_traverse
target: [design_exploration]
description: |
  Full hierarchy traversal pattern for searching within module boundaries.
  Uses BFS with internal_scope_handles() but EXCLUDES child module instances.
  Scopes are pre-located in SCOPE_FILE_PATH (one per module definition).
match_conditions:
  scope_mode: ["full_traverse"]
---

## When to Use
- User asks for objects "in the design" or "in all modules"
- User asks for recursive/deep traversal keywords like "recursively", "all levels"
- Design-wide search where scopes cover all module definitions

## Pre-located Scopes
- `SCOPE_FILE_PATH` contains representative instance paths (one per module definition)
- `OUTPUT_JSON_PATH` is where results should be written
- Each scope represents a different module definition - child instances are covered by other lines

## Key Concept: BFS Within Module Boundary
Use BFS to traverse internal scopes (named blocks, always blocks, generate blocks, etc.)
but **EXCLUDE child module instances** because they are already in SCOPE_FILE_PATH.

```python
def is_instance(handle):
    return handle.type() in ["npiModule", "npiInterface", "npiPackage", "npiProgram"]
```

## Key APIs
- `lang.handle_by_name(scope_path, None)` - Get scope handle by name
- `scope_hdl.net_handles()` - Get nets in this scope
- `scope_hdl.array_net_handles()` - Get array nets in this scope
- `scope_hdl.variables_handles()` - Get variables in this scope
- `scope_hdl.internal_scope_handles()` - Get internal scopes (filter out instances!)
- `collections.deque` - For BFS queue

## Steps

### Step 1: Read scopes and define instance filter
```python
from collections import deque
from pynpi import lang

def is_instance(handle):
    return handle.type() in ["npiModule", "npiInterface", "npiPackage", "npiProgram"]

with open(SCOPE_FILE_PATH, "r") as f:
    scope_paths = [line.strip() for line in f if line.strip()]
```

### Step 2: BFS for each scope (excluding child instances)
```python
results = []
for scope_path in scope_paths:
    scope_hdl = lang.handle_by_name(scope_path, None)
    if scope_hdl is None:
        continue
    queue = deque([scope_hdl])
    while queue:
        current = queue.popleft()
        # Collect signals from current scope
        for hdl in list(current.net_handles()) + list(current.array_net_handles()) + list(current.variables_handles()):
            name = hdl.name()
            if user_filter_matches(name):  # e.g., 'clk' in name
                results.append({"identifier": hdl.full_name(), "attributes": {...}})
        # Add internal scopes to queue, but SKIP child instances
        for child in current.internal_scope_handles():
            if not is_instance(child):
                queue.append(child)
```

### Step 3: Write JSON output
```python
import json
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## IMPORTANT
- **ALWAYS filter out instances** from internal_scope_handles() when using BFS
- Instance types to exclude: `npiModule`, `npiInterface`, `npiPackage`, `npiProgram`
- Internal scopes to INCLUDE: named blocks, always blocks, generate blocks, etc.
- This approach finds ALL signals within each module definition's boundary
- The union of all scopes = complete design results
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
