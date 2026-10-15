---
name: search_and_filter_signals
description: |
  Search, list, query, and filter signals in FSDB files based on various criteria including scope location, signal name patterns, signal types, directions, and module names.
  
  Key distinctions:
  - `target_scope`: The full hierarchical scope path to START searching FROM (e.g., 'tb_CPUsystem.i_CPUsystem.i_CPU'). If the user provides the scope completely (full path), put that full path here.
  - `scope_name_pattern`: A wildcard pattern to FILTER signals by their immediate parent scope's local name (e.g., 'i_*'). If the user already provided a complete scope path, do NOT use `scope_name_pattern`—use `target_scope` only.
  
  Important notes:
  - When the user provides a FULL signal path (e.g. `system.CHILD1.En_A`) and asks if it exists or asks about its status, prefer calling `is_signal_exist(signal_name='system.CHILD1.En_A')` for a fast O(1) lookup instead of splitting into scope+leaf for `search_signal()`. This is especially important on large FSDBs (load-scopes-on-demand) where `search_signal()` without a narrow scope can cause out-of-memory.
  - 'all signals' does NOT mean recursive search unless combined with explicit scope depth keywords like 'recursively' or 'child scopes'.
  - Only search from root with `include_child_scopes=True` when the user wants "exists anywhere" and does NOT provide a specific parent scope.
  - If the user says "in/within/under <scope>" and asks to list signals in that scope, default to `include_child_scopes=False` (depth 1). Use `include_child_scopes=True` only when the prompt explicitly says "recursively", "hierarchy", or "child scopes".
  - `search_signal()` returns a matching-signals list file path (`file_path`). If a downstream waveform tool supports `signal_file`, prefer passing this `file_path` as `signal_file` instead of expanding a long `signal_names` list.
target: [waveform]
examples:
  - "List signals under <scope_name> in <fsdb_file>."
  - "List signals directly under <scope_name> without including its sub-scopes in <fsdb_file>."
  - "Find signals that contain '<pattern>' under <scope_name> in <fsdb_file>."
  - "Find signals under <scope_name> where the immediate parent scope local name contains '<pattern>' in <fsdb_file>."
  - "Find signals under <scope_name> where the module name is <module_name> in <fsdb_file>."
  - "List signals with direction inout under <scope_name> in <fsdb_file>."
  - "List assertion signals under <scope_name> in <fsdb_file>."
  - "List power signals under <scope_name> in <fsdb_file>."
  - "Find all signals with name matching '*addr*' in <fsdb_file>."
  - "List ports under <scope_name> and its child scopes recursively in <fsdb_file>."
  - "Find signals at the top level of <scope_name> in <fsdb_file>."
  - "List signals under <scope_name> with depth 1 in <fsdb_file>."
  - "List registers under <scope_name> recursively in <fsdb_file>."
  - "List nets under <scope_name> recursively in <fsdb_file>."
  - "Check if <signal_full_path> exists in <fsdb_file>."
  - "Does signal <signal_full_path> exist in <fsdb_file>?"
  - "Find and report the status of this signal: <signal_full_path>"
  - "Full scope is <scope_path>. List signals under it in <fsdb_file>."
  - "List all signals under <target_scope> hierarchy"
---

## Steps
- 0. If the user provides a full hierarchical signal path and the intent is an existence check or status report: call `is_signal_exist(signal_name=<full_path>)` first. If it returns `"Signal Exists": true`, proceed to use the signal with downstream tools. If it returns a fail reason, report to the user that the signal was not found at the given path — do NOT search for alternatives, do NOT broaden the scope, do NOT call `search_signal()` or `search_scope()`. Just report the failure.
- 1. Call `search_signal()` with appropriate parameters determined from the user query
- 2. Determine `target_scope` (where to start searching):
- 2.a. If the user provides a COMPLETE scope path (e.g. 'full scope is <scope>', 'scope is <scope>', 'full scope: <scope>', 'target scope is <scope>'), set `target_scope=<full_hierarchical_path>` exactly. Do NOT use `scope_name_pattern` in this case.
- 2.b. If user specifies 'under <scope>', 'in <scope>', 'at <scope>' and the scope is clearly a full hierarchical path, use `target_scope=<full_hierarchical_path>`
- 2.c. If searching from root or no scope specified, omit `target_scope` (defaults to root)
- 3. Determine `include_child_scopes` (search depth):
- 3.a. Check for explicit depth keywords first:
- 3.a.i. 'recursively', 'recursive', 'hierarchy', 'hierarchical', 'and its child scopes', 'and sub-scopes', 'all child scopes', 'including child scopes', 'in the entire FSDB', 'in the whole FSDB', 'anywhere in the FSDB', 'across all scopes', 'all scopes', 'any scope', 'any module', 'in the whole design', 'across the hierarchy', 'globally', 'everywhere' -> `include_child_scopes=True`
- 3.a.ii. 'directly under', 'without sub-scopes', 'at the top level', 'with depth 1', 'depth 1 only' -> `include_child_scopes=False`
- 3.b. If no explicit depth keyword, determine based on scope presence (a hierarchical design path like 'tb.dut.cpu'):
- 3.b.i. Scope keywords: 'under <scope>', 'in <scope>', 'at <scope>', 'within <scope>', 'inside <scope>', 'from <scope>', 'for <scope>', 'of scope <scope>', 'of <scope>'.
  'in <fsdb_file>' (e.g. 'in gate.fsdb', 'in CPU.fsdb', 'in the active FSDB') is the FSDB filename, not a scope, so it does not cap depth.
- 3.b.ii. If a true scope keyword is found -> `include_child_scopes=False` (depth 1 from that scope).
- 3.b.iii. If no true scope keyword (or only an FSDB reference) is found -> `include_child_scopes=True` (search entire hierarchy).
- 3.c. Examples:
  - 'List signals within system.i_cpu scope' -> `include_child_scopes=False`
  - 'List signals under tb.cpu' -> `include_child_scopes=False`
  - 'List signals under tb.cpu recursively' -> `include_child_scopes=True`
  - 'Find all signals with *addr*' -> `include_child_scopes=True`
  - 'List signals in the entire FSDB' -> `include_child_scopes=True`
  - 'In gate.fsdb, find signals named clk' -> `include_child_scopes=True` ('in gate.fsdb' is the FSDB, not a scope)
- 4. Determine `signal_name_pattern` (signal name filtering):
- 4.a. Determine whether the user intent is exact name matching or conceptual signal search:
  - Exact-name intent: user says "signal name is <name>", "named <name>", or uses quotes/backticks around the token (for example `"clock"`, `'clock'`, or `` `clock` ``). In this case, use the exact token first (for example `signal_name_pattern=clock`) and do not expand to aliases unless the user explicitly asks for alternatives.
  - Concept intent: user asks for a role/type signal (for example "find the clock signal"). In this case, you MUST run exact-token-first before aliases:
    - first try the literal token from user wording (for example `clock`),
    - only if zero matches, retry with aliases/patterns (for example `clk`, `clk*`, `*clk*`).
  - For paired checks like "clock and reset", apply the same two-stage rule to each term independently (`clock` then `clk*`; `reset` then `rst*`).
- 4.b. If user explicitly includes wildcards (e.g., '*addr*'), keep them as given.
- 4.c. Use wildcards: '*' for any characters, '?' for single character
- 4.d. Do NOT include bit range (use 'data' not 'data[7:0]')
- 4.e. If user provides a FULL signal path (e.g. `system.CHILD1.En_A`), set:
      - `target_scope=system.CHILD1`
      - `signal_name_pattern=En_A`
- 5. Determine `scope_name_pattern` (filter by parent scope's local name):
- 5.a. Only use this when the user explicitly wants to FILTER by the immediate parent scope's local name (e.g., 'scope name contains CCU').
- 5.b. If the user provides a complete hierarchical scope path, do NOT use `scope_name_pattern`; set `target_scope` to that full path instead.
- 5.c. Use local scope name only, not full path
- 6. Determine `module_name_pattern` (filter by module name):
- 6.a. If user specifies module name (e.g., 'module name is PCU'), use `module_name_pattern=<pattern>`
- 7. Determine `signal_direction` (filter by direction):
- 7.a. If user specifies direction, use `signal_direction` as a list
- 7.b. Examples: `signal_direction=['input']`, `signal_direction=['inout']`, `signal_direction=['input', 'output']`
- 7.c. 'ports' means input or output: `signal_direction=['input', 'output']`
- 8. Determine `signal_type` (filter by type):
- 8.a. Valid types: 'register', 'net', 'assertion', 'power', 'string'
- 8.b. Examples: 'registers' -> `signal_type=['register']`, 'nets' -> `signal_type=['net']`
- 9. Report the matching signals from `search_signal()` result
