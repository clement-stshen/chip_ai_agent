---
name: search_signals_by_value_or_transition
description: |
  Query and filter signals by conditions (name pattern, direction, type) and check their values or transitions at specific timestamps or within time ranges.
target: [waveform]
examples:
  - "List signals under <scope_name> with their values at <timestamp>."
  - "Find signals with <name_pattern> that equal to 1'b0 between <start_time> and <end_time>."
  - "Give me the signals having value change at <timestamp>."
  - "Print all input signals having value change event at <timestamp>."
  - "Which signals under <scope_name> have value transition to 8'hff after <start_time>."
---

## Steps
- 1. Traverse and filter signals by `search_signal()` with given conditions, such as name pattern, direction, type, etc.
- 1.a. When calling `search_signal()`, set `include_child_scopes` per the rules in `search_and_filter_signals` (True when the user says 'recursively' / 'hierarchy' / 'child scopes' / 'entire FSDB' / 'anywhere in FSDB' / 'across all scopes' / 'everywhere'; True when no scope is specified at all; False only when a true hierarchical scope path is given). 'in <fsdb_file>' is NOT a scope.
- 2. Determine temporal range if any to search values/events and choose the correct time argument names for each tool.
- 2.a. For `find_signal_value_change_event()` and `find_signal_transition_to_value()`, use `reference_time` and `stop_time` to bound a time window (do not use `start_time`/`end_time`).
- 2.b. For tools that truly use `start_time`/`end_time` (e.g. sequence/unknown-value style tools), use those fields as defined by the tool schema.
- 3. Choose proper function to search values or events among time range. All four tools below accept multiple signals at once via `signal_file` or `signal_names: list[str]`. Call them with the full set of matching signals from step 1; do not loop one signal at a time.
- 3.a. For checking values at a single timestamp, use `get_signal_value_at_time(signal_file=<match_file>)` (or `signal_names=[...]`).
- 3.b. For checking existance of unknown value (x), use `find_first_unknown_value(signal_file=<match_file>)` (or `signal_names=[...]`).
- 3.c. For matching a certain target value, use `find_signal_transition_to_value(signal_file=<match_file>)` (or `signal_names=[...]`).
- 3.d. For finding value changes without specific value, use `find_signal_value_change_event(signal_file=<match_file>)` (or `signal_names=[...]`).
- 3.e. Prefer `signal_file=<match_file>` (the file produced by `search_signal()`) over `signal_names=[...]` whenever the matching signal list came from a `search_signal()` call, since it avoids re-listing signals.
- 4. Only report the signals and values satisfying all the given conditions.
