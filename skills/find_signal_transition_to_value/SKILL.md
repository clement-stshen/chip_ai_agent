---
name: find_signal_transition_to_value
description: |
  Find transitions of one or more signals to a specific target value, optionally within a time range and/or under a condition.
target: [waveform]
examples:
  - "When does <signal> go to <to_value> between <start_time> and <end_time> in <fsdb_file>?"
  - "How many times does <signal> transition to <to_value> in <fsdb_file> from <start_time> to <end_time>?"
  - "List all timepoints when <signal> becomes <to_value> in <fsdb_file>."
  - "When does <signal> go high between <start_time> and <end_time> in <fsdb_file>?"
  - "In <fsdb_file>, count transitions of <signal> from <from_value> to <to_value>."
  - "How many occurrences of <to_value> in <signal> are there in <fsdb_file>?"
  - "In <fsdb_file>, find the 5th transition of <signal> to <to_value>."
  - "When is the <n>-th falling edge of signal <signal> in <fsdb_file>?"
  - "In <fsdb_file>, when does <signal> transition to known values of <to_value> from simulation time <start_time> till end of simulation?"
  - "What is the very next transition from <from_value> to <to_value> for signal <signal> after <time> in <fsdb_file>?"
  - "What times does the signal <signal> have the value of <to_value> in <fsdb_file>?"
  - "What's the next transition to <to_value> for signal <signal> after <time> in <fsdb_file>?"
---

## Steps
- 1. Use `find_signal_transition_to_value()` when the prompt specifies a target value the signal transitions to.
- 1.a. If no target value is specified, use `find_signal_value_change_event()` instead.
- 2. Decide the waveform file: if the prompt mentions current/active waveform (e.g., 'current waveform', 'active waveform', 'current FSDB'), omit `filename` (or set it to None) so the tool uses the active FSDB in nWave.
- 3. Decide the target signal(s):
- 3.a. If you already have a matching-signals list file from `search_signal()` (its result `file_path`), pass it via `signal_file=<that_file_path>` and omit `signal_names`.
- 3.b. If the prompt provides explicit signal names, pass them via `signal_names`.
- 3.c. If the prompt mentions selected signals (e.g., 'selected signal', 'selected signals', 'current selection'), omit `signal_names` (or set it to None) so this tool uses the currently selected signal(s) as input.
- 4. Decide the target value: set `to_value=<to_value>` (use Verilog-style literals if applicable, e.g. 8'hff, 1'b1).
- 4.a. If the prompt specifies 'from <from_value> to <to_value>', also set `from_value=<from_value>`.
- 5. Decide the reference time:
- 5.a. If the prompt provides an explicit time, pass it via `reference_time`.
- 5.b. If the prompt mentions cursor time (e.g., 'cursor', 'cursor time', 'from cursor'), set `reference_time` to the literal string 'cursor'.
- 6. Decide direction: next/after -> `search_forward=True`; previous/before -> `search_forward=False`.
- 7. For next/previous/after/before transition queries, set `exclude_reference_time=True` (exclusive).
- 7.a. For inclusive wording like 'at or after', 'at or before', or 'including <time>', keep `exclude_reference_time=False`.
- 8. For an exact-time query like 'at <time>', set `reference_time=<time>`, `stop_time=<time>`, and keep `exclude_reference_time=False`.
- 9. For a bounded time range query, set `reference_time=<start_time>` and `stop_time=<end_time>`.
- 10. Decide output mode: for a count only, set `count_only=True`; otherwise keep `count_only=False` to return transition timestamps.
- 11. Decide event count (how many matching transitions to return). This rule applies ONLY when `count_only=False`:
- 11.a. If the user asks for the N-th transition (e.g., '5th transition', 'the 3rd rising edge', '<n>-th time it becomes 1'):
  - set `event_count=<n>` so the tool returns the first N matching transition timestamps
  - after the tool returns, use the N-th timestamp from the returned list as the answer (not the 1st)
- 11.b. If the user asks to "show N transitions", set `event_count=<n>` and present all returned timestamps.
- 11.c. If the user asks to list/show all/every transition, set `event_count=0`.
- 11.d. Otherwise, set `event_count=1` (first matching transition).
- 12. If the prompt includes a filter like 'while/when <condition>', set `condition=<condition>`.
- 13. If the user explicitly wants the cursor at the N-th transition time, call `set_cursor_time(time_str=<nth_timestamp>)` after extracting it.
