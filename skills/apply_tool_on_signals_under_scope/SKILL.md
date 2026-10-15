---
name: apply_tool_on_signals_under_scope
description: |
  Use when the user asks to ADD, FIND, CHECK, COUNT, or otherwise ACT ON signals located under a scope (e.g., "add signals under tb.cpu to nWave", "find first unknown of signals under tb.cpu", "add counters for signals under tb.cpu"). Two-step internally: `search_signal()` to identify the matching signals, then the chosen downstream tool (`add_signals`, `find_first_unknown_value`, `add_counter`, etc.) on that set. Do NOT use this skill for plain "list signals under <scope>" prompts \u2014 those belong to `list_signals`.
target: [waveform]
examples:
  - "Add signals under scope <scope_name> to nWave."
  - "Add signals under scope <scope_name> to nWave in <fsdb_file>."
  - "Add signals under scope <scope_name> hierarchy to nWave."
  - "Add signals matching '*pattern*' under <scope_name> to nWave."
  - "Find the first unknown value of the signals under <scope_name>."
  - "Find the first unknown value of signals with '<pattern>' in name under <scope_name>."
  - "Add counters for signals under <scope_name> in <fsdb_file>."
---

## Steps
- 1. Stage A (find signals): call `search_signal(filename=<fsdb_file>, target_scope=<scope_name>, include_child_scopes=False, signal_name_pattern=<pattern_if_any>, ...)` to find matching signals under the given <scope_name>.
- 1.a. Set `target_scope=<scope_name>` exactly (full hierarchical scope path).
- 1.b. Set `include_child_scopes` per the rules in `search_and_filter_signals` (True when the user says 'recursively' / 'hierarchy' / 'child scopes' / 'entire FSDB' / 'anywhere in FSDB' / 'across all scopes' / 'everywhere'; False otherwise when a true hierarchical scope path is given). The word 'under' alone does NOT include child scopes; 'in <fsdb_file>' is NOT a scope.
- 1.c. Apply any additional filters (signal name, type, direction) as needed from the prompt.
- 1.d. Capture `<match_file>` from the `search_signal()` result `file_path` (matching-signals list file).

- 2. Stage B (apply tool): choose the signal input method with highest priority:
- 2.a. If the downstream tool supports a `signal_file` argument, pass `signal_file=<match_file>` and omit `signal_names`.
- 2.b. Otherwise, use the returned signal list as `signal_names` (full hierarchical signal paths).

- 3. Execute the downstream tool(s) using the signals from step 2. Inspect the tool's schema to decide how to pass the signals (in this priority order):
- 3.a. If the tool has a `signal_file` parameter, call the tool with `signal_file=<match_file>` and omit `signal_names`. This is the preferred form whenever available.
- 3.b. Else if the tool has a list-typed parameter (`signal_names: list[str]`, `signals: list[...]`, etc.), call the tool with the full list of matching signals.
- 3.c. Only when the tool truly accepts a single signal (e.g., a scalar `signal_name: str`), call the tool once per signal in a loop.
- 3.d. Only open UI elements like the GetSignal form or the signal browser when the user explicitly asks.
- 3.e. For "add signals to nWave" requests, call `add_signals(signal_names=<matching_signals_list>)` directly. If the user asked for a group, set `group=<group_name>`. If the user asked for a specific nWave window, set `window=<window>`.
- 3.f. For "add counter" requests, call `add_counter(signals=<matching_signals_list>)` directly. Map edge wording: 'rising'→`type='Rising'`, 'falling'→`type='Falling'`, 'any change'→`type='AnyChange'`.
- 3.g. Examples:
-     - 'Find the first unknown value of signals under <scope>' -> call `find_first_unknown_value(signal_file=<match_file>)` once; return the earliest unknown across results.
-     - 'Add signals under <scope> to nWave' -> call `add_signals(signal_names=<matching_signals_list>)` once.
-     - 'Add counters for signals under <scope>' -> call `add_counter(signals=<matching_signals_list>)` once.
