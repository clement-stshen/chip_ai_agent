---
name: add_signals
description: |
  Add one or more explicitly named signals to the nWave waveform window.
  Use when the user provides specific signal names or refers to previously found signals.
  This recipe requires signal names to already be known — it does NOT search for signals by scope.
target: [waveform]
examples:
  - "Add system.i_cpu.ALU and system.i_cpu.alu_mode to nWave."
  - "Show these signals in the waveform: <signal_list>."
  - "Add the results from the previous search to nWave."
  - "Add selected signals to nWave."
---

## Steps
- 1. Decide how to get the signal list:
- 1.a. If the user provides explicit full signal paths, pass them directly to `add_signals(signal_names=[...])`.
- 1.b. If the user refers to signals found by a prior step (e.g., "add those signals", "add the results"), reuse that list as `signal_names`.
- 1.c. If the user says "add selected signals", omit `signal_names` and use the tool that consumes current selection (do NOT invent Tcl). If no such tool is applicable, ask the user to name the signals or scope.

- 2. Call `add_signals()`:
- 2.a. `add_signals(signal_names=<list_of_full_signal_paths>)`
- 2.b. Optionally set `group=<group_name>` only if the user asks to group the added signals.
- 2.c. Optionally set `window=<window>` only if the user specifies a particular nWave window.

- 3. Hard rules:
- 3.a. Do NOT call raw Tcl as part of this workflow; use the `add_signals()` tool.
- 3.b. Do NOT call `wvAddAllSignals` unless the user explicitly asks to add all signals.
- 3.c. Do NOT pass a scope path as a signal name. A scope path is NOT a signal.
