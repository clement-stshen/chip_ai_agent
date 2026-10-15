---
name: lang_limited_scope_traverse
target: [design_exploration]
description: |
  Limited scope traversal for object types that don't have *_handles() methods.
  Use hier_tree_trv with skip callbacks to stay within one scope.
match_conditions:
  scope_mode: ["scope_based", "limited_traverse"]
  needs_hier_tree_trv_type: true
---

## When to Use
User asks for objects "in" a scope, but the object type has no `*_handles()` method:
- npiAlways (always blocks)
- npiInitial (initial blocks)
- npiForce, npiRelease (force/release statements)
- npiAssignStmt (assign statements)
- Statement types in general (npiIf, npiWhile, npiCase, etc.)
- npiTaskCall, npiFuncCall (task/function calls)

## Key APIs
- `lang.hier_tree_trv_register_cb(npi_type, callback, cb_data)` - Register for target type
- `lang.hier_tree_trv_chk_skip_cb(npi_type, skip_callback, cb_data)` - Register skip callback
- `lang.hier_tree_trv(scope_name)` - Start traversal
- `lang.hier_tree_trv_reset_cb()` - Reset all registered callbacks

## Callback Function Rules (CRITICAL)

### Collect Callback Signature
```python
def collect_cb(hdl, cb_data):
    # hdl: handle to the found object
    # cb_data: list to store collected information
```

**Rules:**
1. First parameter `hdl` is a handle to the found object
2. Second parameter `cb_data` is a list for storing collected information
3. **CRITICAL**: If you need to store the handle itself (not just its data), you MUST call `hdl.set_permanent()` BEFORE appending, or the handle becomes invalid after the callback returns
4. Callback does NOT allow any other parameters - use global variables for additional context
5. Callback should NOT return any value (return value is ignored)

### Skip Callback Signature
```python
def skip_cb(hdl, cb_data):
    # Return True to SKIP (don't traverse into this scope)
    # Return False to CONTINUE (traverse into this scope)
    return True or False
```

**Example: Keep handles permanently**
```python
results = []
def collect_cb(hdl, cb_data):
    hdl.set_permanent()  # MUST call before storing handle
    cb_data.append(hdl)
```

## Steps

### Step 1: Define skip callback
For "in scope" queries: skip all instance scopes EXCEPT the root scope:
```python
root_scope = "<target_scope_full_name>"
def skip_cb(hdl, cb_data):
    full_name = hdl.full_name()
    if full_name and full_name != root_scope:
        return True  # Skip child instances
    return False  # Don't skip root
```

### Step 2: Define collect callback
```python
results = []
def collect_cb(hdl, cb_data):
    # Example: collect file and line info
    cb_data.append({
        "identifier": f"{hdl.file()}:{hdl.line_no()}",
        "type": hdl.type()
    })
```

### Step 3: Register callbacks
1. Register collect callback for target type (e.g., npiAlways, npiCase)
2. Register skip callback for ALL instance types:
   - npiModule, npiInterface, npiPackage, npiProgram

```python
lang.hier_tree_trv_register_cb("npiCase", collect_cb, results)
lang.hier_tree_trv_chk_skip_cb("npiModule", skip_cb, [])
lang.hier_tree_trv_chk_skip_cb("npiInterface", skip_cb, [])
lang.hier_tree_trv_chk_skip_cb("npiPackage", skip_cb, [])
lang.hier_tree_trv_chk_skip_cb("npiProgram", skip_cb, [])
```

### Step 4: Traverse and cleanup
```python
lang.hier_tree_trv(root_scope)
lang.hier_tree_trv_reset_cb()
# Process results
lang.release_all_handles()
```

## IMPORTANT
- This is the ONLY way to get types like npiAlways, npiCase, npiForce within a single scope
- Without skip callbacks, hier_tree_trv goes to ALL descendants
- The skip callback checks if the instance's full_name equals root_scope to allow the root itself
- Always call `hier_tree_trv_reset_cb()` after traversal to clean up
