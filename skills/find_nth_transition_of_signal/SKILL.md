---
name: find_nth_transition_of_signal
description: Get the timestamp of the <n-th> transition event of a <signal>, with optional <reference time> and <target value>.
target: [waveform]
examples:
  - What is the first rising of <signal>?
  - Tell me the 10th time when <signal> becomes <value> after <reference time>.
---

## Steps
- 1. Determine if a target value is specified or not.
- 1.a. If specified, call `find_signal_transition_to_value()`.
- 1.b. If not specified, call `find_signal_value_change_event()`.
- 2. Specify `event_count` to get the first <n-th> events.
- 3. Get the timestamp of the last event if exists.
