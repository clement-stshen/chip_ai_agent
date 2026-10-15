---
name: get_signal_switching_statistics
description: >-
  Compute timing/statistical data for a 1-bit signal: duty cycle, total time
  at high (logic 1), total time at low (logic 0), and number of transitions.
  Use whenever the user asks about how long a signal stayed high/low, its
  duty cycle, or signal switching statistics.
target: [waveform]
examples:
  - "What's the duty cycle of the selected signal?"
  - "What's the duty cycle of <signal>?"
  - "How long did <signal> stay high?"
  - "How much time was <signal> at logic 1?"
  - "Total time <signal> spent at high/low."
  - "Get the signal switching statistics for <signal>."
---

## Steps
- 1. Call `get_signal_switching_statistics()` directly when the prompt
  mentions duty cycle / time-high / time-low / switching statistics /
  signal duration at a value.
- 2. Signal selection:
  - 2.a. If the user named one or more signals explicitly, pass them via
    `signal_names=[<name>, ...]` exactly as the user wrote them.
  - 2.b. If the user said "selected signal" or omitted the signal name,
    also omit `signal_names`. The tool defaults to the currently selected
    signals in nWave.
- 3. Time range:
  - 3.a. DEFAULT to the full FSDB range by leaving `start_time` and
    `end_time` unset. The tool already covers the entire dump by default.
  - 3.b. Do NOT call `get_info()`, `get_selected_time_range()`, or any
    other tool to discover the time range first — that is unnecessary and
    can fail in environments where the FSDB path differs between the
    nWave session and the filesystem.
  - 3.c. Only set `start_time` / `end_time` when the user explicitly
    specifies a time window.
- 4. Do NOT call `set_active_fsdb()` as a preparatory step. If the user
  named an FSDB file, pass it via `filename`; otherwise omit it.
- 5. CRITICAL: this tool only works for 1-bit signals. If the user asks
  about a multi-bit bus, surface that limitation rather than calling the
  tool with an unsupported signal.
