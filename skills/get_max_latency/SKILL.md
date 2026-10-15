---
name: get_max_latency
description: Get the maximum latency (response time) from a trigger signal transition to a response signal transition.
target: [waveform]
examples:
  - Check the max response time from <trigger_signal> (<from_value> to <to_value>) to <response_signal> (<from_value> to <to_value>) in <fsdb_file>.
  - Is there any <response_signal> (<from_value> to <to_value>) that took more than <threshold_time> to respond to <trigger_signal> (<from_value> to <to_value>) in <fsdb_file>?
  - What's the delay between <trigger_signal> and <response_signal> going high in <fsdb_file>?
  - In <fsdb_file>, how long does <response_signal> go high after <trigger_signal> goes high?
---

## Steps
- 1. Use `get_max_latency()` when the prompt asks for maximum/worst-case response time (latency) from one signal transition to another.
- 2. Decide the waveform file: if the prompt mentions current/active waveform (e.g., 'current waveform', 'active waveform', 'current FSDB'), omit `filename` (or set it to None) so the tool uses the active FSDB in nWave.
- 3. Decide the trigger transition:
- 3.a. Set `trigger_signal=<trigger_signal>`.
- 3.b. Set `to_value_of_trigger_signal=<to_value_of_trigger_signal>` (e.g., 'go high' means to 1).
- 3.c. If the prompt specifies an explicit from-value (e.g., '0 to 1'), set `from_value_of_trigger_signal=<from_value_of_trigger_signal>`.
- 4. Decide the response transition:
- 4.a. Set `response_signal=<response_signal>`.
- 4.b. Set `to_value_of_response_signal=<to_value_of_response_signal>` (e.g., 'go high' means to 1).
- 4.c. If the prompt specifies an explicit from-value (e.g., '0 to 1'), set `from_value_of_response_signal=<from_value_of_response_signal>`.
- 5. Call `get_max_latency()` and report the maximum latency and its corresponding start/end time from the tool result.
- 6. If the prompt asks whether any latency exceeds a threshold (e.g., '> 50ns'), compare the reported maximum latency against the threshold and answer yes/no, and include the max latency details.
