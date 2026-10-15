---
name: get_last_value
description: Get the final value of the signal
target: [waveform]
examples:
  - What is the value of the <signal> at the end of simulation
---

## Steps
- 1. Get FSDB <max_time> by `get_info()`.
- 2. Get <value> at <max_time> by `get_signal_value_at_time()`.
