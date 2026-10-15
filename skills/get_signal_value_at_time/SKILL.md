---
name: get_signal_value_at_time
description: |
  Retrieve the value(s) of one or more named signals at a specific timestamp.
  Use this directly when the user names a specific signal (or a small list
  of signals) and asks for its value at a given time -- do NOT call
  `search_signal()` first to "find" a signal that the user already named.
  The framework resolves simple/short names (e.g. `C1`, `clk`, `\TR[6]`)
  against the currently selected scope automatically.

  For "value at simulation begin/end" prefer `get_first_value` /
  `get_last_value`. For "when does <signal> change" prefer
  `find_signal_value_change_event` / `find_signal_transition_to_value`.
target: [waveform]
examples:
  - "Get value of <signal> at <time> in <fsdb_file>."
  - "What's the value of signal <signal> at time <time>?"
  - "Get value of the selected signal at the cursor time."
  - "Show me the value of signal <signal> at <time>."
  - "Get value of <signal>[<n>] at <time> in <fsdb_file>."
  - "What's the value of <signal_a> and <signal_b> at <time> in <fsdb_file>?"
  - "Show the decimal value of <signal> at <time> in <fsdb_file>."
---

## Steps

- 1. Use `get_signal_value_at_time()` whenever the user names a specific
  signal (or a small explicit list of signals) and asks for its value at
  a single timestamp. Skip `search_signal()` -- the framework resolves
  simple/short names against the currently selected scope. Only call
  `search_signal()` first when the user gave a wildcard pattern (e.g.
  `*data*`) or a category description (e.g. "all input signals under
  <scope>") instead of concrete names. Do NOT call `set_active_fsdb()`
  or `import_design()` just to read a value -- the active FSDB is enough.
- 2. Decide the waveform file: if the prompt mentions current/active
  waveform, omit `filename`. Otherwise pass `filename=<fsdb_file>`.
- 3. Decide the target signal(s):
- 3.a. If the prompt provides explicit names (including escaped Verilog
  identifiers like `\TR[6]` and bit/part selects like `bus[3]`,
  `bus[7:0]`), pass them via `signal_names=[<name>, ...]` exactly as the
  user wrote them. Do NOT pre-expand them into full hierarchical paths
  and do NOT prefix them with the active scope.
- 3.b. If the prompt mentions selected signal(s), omit `signal_names` so
  the tool uses the current nWave selection.
- 3.c. If you already have a matching-signals list file from a prior
  `search_signal()` call, pass it via `signal_file=<file_path>` and
  omit `signal_names`.
- 4. Decide the timestamp:
- 4.a. Explicit time -> pass it via `time=<time>` with a unit suffix
  (e.g. `2360ns`, `1.5us`).
- 4.b. Cursor time wording ("at the cursor", "current value") -> set
  `time='cursor'` (literal string). Do NOT call `get_cursor_time()`
  first; the tool resolves it.
- 4.c. No time given -> omit `time`; the tool defaults to the current
  cursor time.
- 5. If the prompt mentions a radix (e.g. "in hex", "as binary",
  "decimal value"), set `radix` to one of `binary` | `octal` |
  `decimal` | `hexadecimal`. Otherwise omit `radix`.
- 6. Report each result with the full hierarchical path returned by the
  tool (e.g. `system.i_cpu.i_PCU.C1`), the requested timestamp, and the
  value. List one signal per line for multi-signal queries.
