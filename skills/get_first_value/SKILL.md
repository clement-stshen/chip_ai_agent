---
name: get_first_value
description: Get the initial value of the signal
target: [waveform]
examples:
  - What is the value of the <signal> at the simulation begin
---

## Steps
- 1. Get FSDB <min_time> by `get_info()`.
- 2. Get <value> at <min_time> by `get_signal_value_at_time()`.
