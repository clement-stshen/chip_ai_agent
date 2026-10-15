---
name: lang_single_level_access
target: [design_exploration]
description: |
  Single-level access pattern for objects "in" a scope.
  Do NOT use hier_tree_trv. Use handle_by_name + *_handles() methods.
match_conditions:
  scope_mode: ["single_level"]
  needs_hier_tree_trv_type: false
---

## When to Use
User asks for objects "in" a scope without recursive keywords like "recursively", "to leaf", "entire".
Also use when user asks for objects "but not in internal scope" or "excluding child instances".

## Key APIs
- `lang.handle_by_name(scope_name, None)` - Get scope handle by full hierarchical name
- `scope_hdl.net_handles()` - Get nets directly in scope
- `scope_hdl.array_net_handles()` - Get array nets directly in scope
- `scope_hdl.variables_handles()` - Get variables directly in scope
- `scope_hdl.port_handles()` - Get ports directly in scope
- `scope_hdl.internal_scope_handles()` - Get internal scopes (filter for instances)

## Steps

### Step 1: Get scope handle
Use `lang.handle_by_name(scope_name, None)` with the full hierarchical name.
Always check if handle is None before proceeding.

### Step 2: Get direct objects using *_handles() methods
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

**Case B: "all signals in module X" (no exclusion mentioned)**
- Use BFS with `collections.deque` to search internal named blocks but NOT sub-instances:
  1. Start with the scope handle in queue
  2. For each scope, collect objects using *_handles() methods
  3. Get `internal_scope_handles()`, filter OUT instance types, add non-instances to queue
  4. Instance types to exclude: npiModule, npiInterface, npiPackage, npiProgram

### Step 4: Print results and cleanup
- Print collected results
- Call `lang.release_all_handles()` at the end

## IMPORTANT
- Do NOT use `hier_tree_trv` for this pattern (use limited_scope_traverse skill if type requires it)
- Internal scopes include named blocks, generate scopes, etc. - traverse these but NOT sub-instances
- Always use full hierarchical name for `handle_by_name`, not definition name
