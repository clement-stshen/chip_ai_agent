---
name: add_counter
description: |
  Add counter(s) in nWave for one or more signals. This is a UI action: it adds a visual counter row in nWave and does not compute/report a numeric count in chat.
  
  Use this when the user explicitly asks to add a counter in nWave (optionally constrained to a scope), e.g. 'add a rising edge counter for <signal>'
target: [waveform]
examples:
  - "Add a counter for <signal> in <fsdb_file>."
  - "Add a rising edge counter for <signal> in <fsdb_file>."
  - "Add counters for these signals: <signal_list>."
  - "In the selected/current scope, add counters for signals matching <pattern>."
---

## Steps
- 1. Confirm intent is UI counter creation in nWave (NOT a counting query). If user asks 'how many times', do NOT use `add_counter()`; use transition/value-change tools instead.
- 2. Decide the waveform file: if prompt provides <fsdb_file>, pass it as `filename`. Otherwise omit `filename` to use the active FSDB.
- 3. Decide the target signals:
- 3.a. If user explicitly names signal(s), pass them as `signals` to `add_counter()`.
- 3.b. If user refers to signals found by a prior step (e.g., "add counters for those signals"), reuse that list as `signals`.
- 3.c. Do NOT call `search_signal()` just to pre-validate the signal name(s) before calling `add_counter()`.
- 4. Map edge wording to counter type for `add_counter(type=...)`:
- 4.a. 'rise', 'rising edge', 'go high' -> `type='Rising'`.
- 4.b. 'fall', 'falling edge', 'go low' -> `type='Falling'`.
- 4.c. 'toggle', 'any change', 'value change' -> `type='AnyChange'`.
- 5. Call `add_counter(signals=<signals>, filename=<fsdb_file_or_None>, type=<AnyChange/Rising/Falling>)` to add the counter(s) in nWave.
