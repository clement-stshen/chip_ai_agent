---
name: lang_wildcard_handling
target: [design_exploration]
description: |
  Handle wildcard patterns in scope or object names.
  Do NOT treat '*' or '?' as literal strings - they are wildcard patterns.
match_conditions:
  has_wildcard: true
---

## When to Use
User request contains wildcard characters `*` or `?` in scope or object names.
Examples: "signals in top.mod_*", "instances matching CPU*", "top.*.clk"

## Key APIs
- `lang.handle_by_name(parent_scope, None)` - Get parent scope handle
- `scope_hdl.internal_scope_handles()` - Enumerate children for wildcard matching
- Python `fnmatch.fnmatch(name, pattern)` - Match wildcard patterns

## Steps

### Step 1: Identify wildcard position
Parse the path to find which segment contains wildcard.
- Example: `top.mod_*.sub_*` → wildcards at segment 2 (mod_*) and segment 3 (sub_*)
- Example: `top.cpu.sig_*` → wildcard at segment 3 (sig_*)

### Step 2: Resolve parent scope (prefix before first wildcard)
Get handle for the concrete prefix BEFORE the first wildcard segment.
- For `top.mod_*`, parent is `top`
- For `top.cpu.mod_*`, parent is `top.cpu`
Use `lang.handle_by_name(parent_scope, None)` to get the handle.

### Step 3: Enumerate and filter children
For each wildcard segment:
1. Get `internal_scope_handles()` from current scope
2. Filter by instance types if searching for instances (npiModule, npiInterface, npiPackage, npiProgram)
3. Match `hdl.name()` against wildcard pattern using `fnmatch.fnmatch()`
4. Collect matched handles

### Step 4: Iterate for multi-level wildcards
If path has multiple wildcard segments (e.g., `top.mod_*.sub_*`):
1. Process first wildcard segment, collect matched scopes
2. For each matched scope, process next wildcard segment
3. Repeat until all wildcard segments are resolved

### Step 5: Perform operation on matched scopes
Once all wildcards are resolved, perform the requested operation on final matched scopes.

## IMPORTANT
- Do NOT traverse entire design and filter by full_name matching - this ignores the anchored path structure
- Process wildcards left-to-right, resolving each segment before moving to next
- Use `hdl.name()` for local segment matching, NOT `hdl.full_name()`
- `fnmatch` uses shell-style wildcards: `*` matches any characters, `?` matches single character
