---
name: detect_sequence_and_get_previous_transitions
description: Detect a specific sequence/pattern of values on a signal and get the previous transitions of that signal before the sequence occurs.
target: [waveform]
examples:
  - Detect the sequence <value1> -> <value2> -> <value3> on <signal> and get the previous <n> transitions of it.
  - Check if <signal> goes through the pattern <value1> to <value2> and provide the last <n> transitions before the pattern.
---

## Steps
- 1. Get <time> by `detect_signal_sequence()` for the specific sequence on <signal>.
- 1.a. If cannot find <time> for the sequence, then report not found and stop.
- 1.b. If found <time>, proceed to the step 2.
- 2. Get the previous <n> transitions before <time> by `find_signal_value_change_event()`.
- 2.a. Specify `reference_time` as <time>
- 2.b. Specify `event_count` as <n>
- 2.c. Specify `search_forward` as False
- 2.d. Specify `exclude_reference_time` as True
- 2.e. Do not specify `stop_time`. Any sequence-window constraint from step 1 (e.g., "after 5000ns") applies only to the pattern detection, not to this back-lookup. Set `stop_time` only if the user explicitly bounded the back-lookup itself (e.g., "previous transition between 100ns and 500ns").
- 3. Report the <n> transitions found in step 2.
