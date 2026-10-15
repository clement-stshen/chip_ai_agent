---
name: calculate_signal_duration
description: |
  Calculate the length of time span of a <signal> staying at a certain <value> from <reference_time>.
target: [waveform]
examples:
  - "How long does <signal> stay <value> from <reference_time>?"
  - "Detect the duration of <signal> stucking at <value> after <reference_time>."
---

## Steps
- 1. Examine whether the intent of the user query is to calculate a single duration.
- 1.a. If user wants to check if any duration longer than threshold, call `detect_state_stall()`.1.b. If user wants to check if any duration shorter than threshold, call `detect_glitches().1.c. Otherwise, continue with the following steps.
- 2. Find the first transition to <value> after <reference_time>.
- 2.a. Use `get_signal_value_at_time()` to check if the <signal> is already at <value> at <reference_time>.
- 2.b. If already at <value>, set <transition_time> as <reference_time>.
- 2.c. If not already at <value>, use `find_signal_transition_to_value()` to find the <transition_time> to the <value>.
- 2.c.1. Specify `exclude_reference_time` as True to avoid getting the same <reference_time> again.
- 2.c.2. Specify `event_count` as 1 to get only the first <transition_time>.
- 3. Find the next transition away from <value> after <transition_time>.
- 3.a. Use `find_signal_value_change_event()` to find the next <value_change_time> after <transition_time>.
- 3.b. Specify `exclude_reference_time` as True to avoid getting the same <transition_time> again.
- 3.c. Specify `event_count` as 1 to get only the first <value_change_time>.
- 4. Calculate the duration by subtracting <transition_time> from <value_change_time>.
