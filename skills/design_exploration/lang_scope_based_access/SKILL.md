---
name: lang_scope_based_access
target: [design_exploration]
description: |
  Scope-based access pattern for objects "in" a scope.
  Do NOT use hier_tree_trv. Use handle_by_name + *_handles() methods.
  Scopes are pre-located in SCOPE_FILE_PATH.
match_conditions:
  scope_mode: ["scope_based"]
  needs_hier_tree_trv_type: false
---

## When to Use
User asks for objects "in" a scope without recursive keywords like "recursively", "to leaf", "entire".
Also use when user asks for objects "but not in internal scope" or "excluding child instances".

## Pre-located Scopes
When this skill is triggered via staged flow:
- `SCOPE_FILE_PATH` contains scope paths (one per line)
- `OUTPUT_JSON_PATH` is where results should be written

## Key APIs
- `lang.handle_by_name(scope_name, None)` - Get scope handle by full hierarchical name
- `scope_hdl.net_handles()` - Get nets directly in scope
- `scope_hdl.array_net_handles()` - Get array nets directly in scope
- `scope_hdl.variables_handles()` - Get variables directly in scope
- `scope_hdl.port_handles()` - Get ports directly in scope
- `scope_hdl.internal_scope_handles()` - Get internal scopes (filter for instances)

## Steps

### Step 1: Read scopes from SCOPE_FILE_PATH (if provided)
```python
with open(SCOPE_FILE_PATH, "r") as f:
    scope_paths = [line.strip() for line in f if line.strip()]
```

### Step 2: Get scope handle and collect objects
Choose appropriate methods based on what user is searching for:
- Signals: `list(net_handles()) + list(array_net_handles()) + list(variables_handles())`
- Ports: `port_handles()`
- Instances: filter `internal_scope_handles()` for types npiModule, npiInterface, npiPackage, npiProgram

### Step 3: Decide on internal scope traversal

**CRITICAL TERMINOLOGY:**
- "internal scope" = named blocks (begin-end with label), generate blocks, always blocks
- "child instances" = sub-module instances (npiModule, npiInterface, npiPackage, npiProgram)

**Case A: "signals but NOT in internal scope" or "excluding internal scope"**
- Use ONLY *_handles() on the main scope, do NOT BFS
- This gives signals directly declared in the module, excluding named blocks

**Case B: "all signals in module X" (no exclusion mentioned) — THIS IS THE DEFAULT**
- Use BFS with `collections.deque` to search internal named blocks but NOT sub-instances:
  1. Start with the scope handle in queue
  2. For each scope, collect objects using *_handles() methods
  3. Get `internal_scope_handles()`, filter OUT instance types, add non-instances to queue
  4. Instance types to exclude: npiModule, npiInterface, npiPackage, npiProgram

**CRITICAL**: When user says "find X in scope Y" without explicitly saying "exclude internal scopes",
ALWAYS use Case B (BFS). This includes parameters, signals, variables, etc.
Do NOT assume "no recursion" — internal scopes are PART of the module.

### WRONG Pattern (NEVER do this):
```python
# WRONG - only searching top-level scope, missing internal scopes
for scope_name in scopes:
    scope_hdl = lang.handle_by_name(scope_name, None)
    for param in scope_hdl.parameter_handles():  # Only gets top-level params!
        ...
# This misses parameters in named blocks, generate blocks, interfaces inside the scope
```

### CORRECT Pattern (BFS into internal scopes):
```python
from collections import deque

INSTANCE_TYPES = {"npiModule", "npiInterface", "npiPackage", "npiProgram"}

for scope_name in scopes:
    scope_hdl = lang.handle_by_name(scope_name, None)
    if scope_hdl is None:
        continue
    queue = deque([scope_hdl])
    while queue:
        current = queue.popleft()
        # Collect from current scope
        for param in current.parameter_handles():
            ...
        # BFS into internal scopes (NOT sub-instances)
        for child in current.internal_scope_handles():
            if child.type() not in INSTANCE_TYPES:
                queue.append(child)
```

### Step 4: Write JSON output
```python
import json
results = [{"identifier": hdl.full_name(), "attributes": {...}} for hdl in collected]
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
```

### Step 5: Cleanup
- Call `lang.release_all_handles()` at the end

## IMPORTANT
- Do NOT use `hier_tree_trv` for this pattern
- Internal scopes include named blocks, generate scopes, etc. - traverse these but NOT sub-instances
- Always use full hierarchical name for `handle_by_name`, not definition name
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
