---
name: find_signal_value_change_event
description: |
  Find any value-change (transition) events of one or more signals, either around cursor/reference time or within a time range. Also handles "last/final/most recent value change" queries.
target: [waveform]
examples:
  - "Find the next transition of <signal> after the cursor time."
  - "Find the previous transition of <signal> before the cursor time."
  - "Show value changes of <signal> at <time> in <fsdb_file>."
  - "Is there a value change of <signal> at <time> in <fsdb_file>?"
  - "Show value changes of <signal> between <start_time> and <end_time> while <condition> in <fsdb_file>."
  - "Show value changes of <signal> at or after <time> (include <time>) in <fsdb_file>."
  - "Show value changes of <signal> at or before <time> (include <time>) in <fsdb_file>."
  - "Show all value changes of <signal> between <start_time> and <end_time> in <fsdb_file>."
  - "How many value changes of <signal> between <start_time> and <end_time> in <fsdb_file>?"
  - "Show <n> consecutive transitions for <signal> starting from <start_time> in <fsdb_file>."
  - "Show <k> value changes before and <m> value changes after <time> for <signal> in <fsdb_file>."
  - "Get the last value change of <signal>."
  - "What is the last value change of <signal>?"
  - "Find the final transition of <signal>."
  - "Get the most recent transition of <signal>."
  - "Last value change of <signal>."
---

## Steps

### Always decide these (steps 1–4):
- 1. Use `find_signal_value_change_event()` when the prompt asks for transitions/value changes but does not specify a target value.
- 2. Decide the waveform file: if the prompt mentions current/active waveform (e.g., 'current waveform', 'active waveform', 'current FSDB'), omit `filename` (or set it to None) so the tool uses the active FSDB in nWave. Otherwise pass the explicit path.
- 3. Decide the target signal(s):
- 3.a. If you already have a matching-signals list file from `search_signal()` (its result `file_path`), pass it via `signal_file=<that_file_path>` and omit `signal_names`.
- 3.b. If the prompt provides explicit signal names, pass them via `signal_names`.
- 3.c. If the prompt mentions selected signals (e.g., 'selected signal', 'selected signals', 'current selection'), omit `signal_names` (or set it to None) so this tool uses the currently selected signal(s) as input.
- 4. Decide event count (how many matching value-change events to return):
- 4.a. If the user specifies a number (e.g., 'show 5 transitions', 'get 10 value changes'), set `event_count=<number>`.
- 4.b. If the user asks to list/show/find all or every value change (e.g., 'list all', 'show all', 'find all', 'every value change', 'all value changes', 'all transitions'), set `event_count=0`.
- 4.c. Otherwise, set `event_count=1` (first matching value change).

### When a reference time or time range is involved (steps 5–10):
- 5. Decide the reference time:
- 5.a. If the prompt provides an explicit time, pass it via `reference_time`.
- 5.b. If the prompt mentions cursor time (e.g., 'cursor', 'cursor time', 'from cursor'), set `reference_time='cursor'`.
- 5.c. If the user asks for the next/previous value change but does not give a time, set `reference_time='cursor'`.
- 6. Decide direction: next/after -> `search_forward=True`; previous/before -> `search_forward=False`.
- 7. For next/previous/after/onwards/before transition queries, set `exclude_reference_time=True` (exclusive) to avoid returning an event at the cursor/reference time.
- 7.a. For inclusive wording like 'at or after', 'at or before', or 'including <time>', keep `exclude_reference_time=False`.
- 8. For a bounded time range query, set `reference_time=<start_time>` and `stop_time=<end_time>`.
- 8.a. For an exact-time query like 'at <time>', set `reference_time=<time>`, `stop_time=<time>`, and keep `exclude_reference_time=False`.
- 8.b. Schema correctness: this tool does not accept `start_time`/`end_time` arguments. Use `reference_time`/`stop_time` instead.
- 9. For a one-sided window of N transitions from a time, set `reference_time=<start_time>` and `event_count=<n>`, and choose direction with `search_forward` (forward for after/next; backward for before/previous).
- 10. For a two-sided window around a time (K-before and M-after), do two one-sided calls: one with `search_forward=False, event_count=<k>` and one with `search_forward=True, event_count=<m>`.

### Optional modifiers (steps 11–12):
- 11. Decide output mode: for a count only, set `count_only=True`; otherwise keep `count_only=False` to return the transition list.
- 12. If the prompt includes a filter like 'while/when <condition>', set `condition=<condition>` using a SystemVerilog boolean expression.
