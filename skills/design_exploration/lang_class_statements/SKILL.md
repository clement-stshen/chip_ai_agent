---
name: lang_class_statements
target: [design_exploration]
description: |
  NPI types for searching statements (always, force, control flow, etc.).
  These types require hier_tree_trv even for single-scope queries.
match_conditions:
  target_object_class: ["statement", "always", "force", "case"]
---

## Statement Class

### IMPORTANT
Most statement types do NOT have `*_handles()` methods.
Must use `hier_tree_trv` with skip callbacks for single-scope queries.
See `lang_limited_scope_traverse` skill for callback rules.

## CRITICAL: hier_tree_trv_register_cb Signature

**ALWAYS use 3 arguments:**
```python
# CORRECT - 3 arguments: (type, callback, cb_data)
lang.hier_tree_trv_register_cb("npiTaskCall", collect_cb, results)
lang.hier_tree_trv_register_cb("npiCase", collect_cb, results)
lang.hier_tree_trv_register_cb("npiForce", collect_cb, results)

# WRONG - 2 arguments (missing type)
lang.hier_tree_trv_register_cb(collect_cb, results)  # ERROR!
```

The **first argument** is REQUIRED and specifies the NPI type to match (e.g., "npiTaskCall", "npiCase", "npiForce").

### Common statement NPI types:

**Always/Initial blocks:**
- npiAlways
- npiInitial

**CRITICAL: always_type() Filtering (Similar to net_type)**

`npiAlwaysComb`, `npiAlwaysFF`, `npiAlwaysLatch` are **NOT** valid NPI types for
`hier_tree_trv_register_cb`. They are only return values of `hdl.always_type()`.

- If the user asks for "always blocks" without specifying a subtype, just register `"npiAlways"`.
- If the user asks for a specific always subtype (e.g., "always_comb"), register `"npiAlways"`
  and filter by `hdl.always_type()` inside the callback.

always_type() return values:
- "npiAlways" - plain `always`
- "npiAlwaysComb" - `always_comb`
- "npiAlwaysFF" - `always_ff`
- "npiAlwaysLatch" - `always_latch`

```python
# CORRECT: register only "npiAlways", filter subtype in callback
def collect_always_comb_cb(hdl, cb_data):
    if hdl.always_type() != "npiAlwaysComb":
        return
    cb_data.append({"identifier": f"{hdl.file()}:{hdl.line_no()}"})

lang.hier_tree_trv_register_cb("npiAlways", collect_always_comb_cb, results)
```

```python
# WRONG - will cause KeyError!
for t in ["npiAlways", "npiAlwaysComb", "npiAlwaysFF", "npiAlwaysLatch"]:
    lang.hier_tree_trv_register_cb(t, cb, results)  # KeyError on npiAlwaysComb!
```

**Assignment statements:**
- npiAssignStmt
- npiAssignment

**Force/Release:**
- npiForce
- npiRelease
- npiDeassign

**Control flow:**
- npiIf
- npiIfElse
- npiWhile
- npiRepeat
- npiWait
- npiCase
- npiFor
- npiForever
- npiDoWhile
- npiForeachStmt

**Other statements:**
- npiAliasStmt
- npiEventStmt
- npiNullStmt
- npiDelayControl
- npiEventControl
- npiDisable
- npiReturnStmt
- npiBreak
- npiContinue

**Immediate assertions (also statements):**
- npiImmediateAssert
- npiImmediateAssume
- npiImmediateCover

## Searching for Statements (Required Pattern)

Since statements have no `*_handles()` methods, you MUST use `hier_tree_trv`:

```python
from pynpi import lang

results = []

def collect_cb(hdl, cb_data):
    # Get file and line for location info
    file_path = hdl.file()
    line_no = hdl.line_no()
    cb_data.append({
        "identifier": f"{file_path}:{line_no}",
        "type": hdl.type()
    })

# For design-wide search with scope file (representatives):
# Register callbacks ONCE before the loop
root_scope = ""
def skip_cb(hdl, cb_data):
    full_name = hdl.full_name()
    if full_name and full_name != root_scope:
        return True
    return False

lang.hier_tree_trv_register_cb("npiCase", collect_cb, results)
lang.hier_tree_trv_chk_skip_cb("npiModule", skip_cb, [])
lang.hier_tree_trv_chk_skip_cb("npiInterface", skip_cb, [])
lang.hier_tree_trv_chk_skip_cb("npiPackage", skip_cb, [])
lang.hier_tree_trv_chk_skip_cb("npiProgram", skip_cb, [])

# Loop: only update root_scope and traverse
for scope_name in scopes:
    root_scope = scope_name
    lang.hier_tree_trv(scope_name)

# Reset ONCE after the loop
lang.hier_tree_trv_reset_cb()
```

## Case Statement Special APIs

When searching for `npiCase` statements:
- `hdl.case_item_handles()` - Get all case items (branches)
- Default branch has NO expr_handles() (empty list)

## Case Without Default Detection (CRITICAL - Read Carefully)

**DO NOT** register multiple statement types when searching for case without default.
**ONLY** register "npiCase" type.

### Step-by-step:
1. Register callback ONLY for "npiCase" type
2. In callback, call `case_item_handles()` to get all branches
3. Check each branch's `expr_handles()` - default branch has NO expressions (empty list)
4. Only collect cases where NO branch has empty expr_handles

### Correct Pattern (MANDATORY):
```python
def collect_case_cb(hdl, cb_data):
    case_items = hdl.case_item_handles()
    has_default = False
    for case_item in case_items:
        expr_items = case_item.expr_handles()
        if not expr_items:  # Empty means default branch
            has_default = True
            break
    if not has_default:
        cb_data.append({
            "identifier": f"{hdl.file()}:{hdl.line_no()}",
            "attributes": {"type": "npiCase", "has_default": False}
        })

# ONLY register npiCase - NOT other statement types
lang.hier_tree_trv_register_cb("npiCase", collect_case_cb, result["objects"])
```

### WRONG Patterns (NEVER do these):
```python
# WRONG 1 - registering multiple statement types
for stmt_type in ["npiAlways", "npiInitial", "npiCase", ...]:
    lang.hier_tree_trv_register_cb(stmt_type, ...)  # NO!

# WRONG 2 - not checking for default
def collect_case_cb(hdl, cb_data):
    cb_data.append(...)  # Missing has_default check!
```

## IMPORTANT
- Never use `scope.stmt_handles()` for statement search - it may not return all statement types
- Always use `hier_tree_trv` with the specific statement type registered
- For single-scope queries, add skip callbacks for npiModule, npiInterface, npiPackage, npiProgram
- For file:line identifiers, the system will automatically calculate expanded count across all instances
