---
name: detect_unknown_and_get_previous_or_next_transitions
description: |
  Detect unknown (x) values on a <signal> and get the previous or next <n> transitions of that <signal> before or after the unknown occurs.
target: [waveform]
examples:
  - "Get the <value> of <signal> before it goes to unknown at <reference_time>."
  - "Find the next transition of <signal> after it becomes unknown at <reference_time>."
---

## Steps
- 1. Confirm whether the unknown value occurs at the <reference_time>.
- 1.a. Call `find_first_unknown_value()` to find if <signal> has unknown value at or after <reference_time>.
- 1.b. specify `start_time` as <reference_time>
- 1.c. specify `exclude_start_time` as False to include <reference_time> itself.
- 1.d. Check the returned result, "Time" field indicates the <unknown_time> of unknown value if found.
- 1.e. If cannot find <unknown_time> or <unknown_time> is not equal to <reference_time>, then report not found and stop.
- 2. Get the previous or next <n> transitions of <signal> around <reference_time>.
- 2.a. Determine if a target value is specified or not.2.a.1. If specified, call `find_signal_transition_to_value()`.
- 2.a.2. If not specified, call `find_signal_value_change_event()`.
- 2.b. Specify `reference_time` as <reference_time>.
- 2.c. Specify `search_forward` as True for next transitions, False for previous transitions.
- 2.d. Specify `exclude_reference_time` as True to avoid getting the same <reference_time> again.
- 2.e. Specify `event_count` as <n>.
- 3. Report the <n> transitions found in step 2.
