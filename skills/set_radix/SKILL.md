---
name: set_radix
description: |
  Set the display radix/format for one or more signals in nWave (Verdi) using `set_radix()`, optionally scoped to a specific nWave window and/or only the selected signal instance.
target: [waveform]
examples:
  - "Set the radix to hex for the selected signals."
  - "Set <signal> to binary."
  - "Set radix of <signal1>, <signal2> to dec in nWave:3."
  - "Set radix to ASCII for <signal> locally (only this instance)."
  - "Set radix to IEEE 754 for <signal>."
  - "Set radix to hex on all signals in nWave"
---

## Steps
- 1. Use `set_radix()` when the prompt asks to change how signal values are displayed in nWave (e.g., "set radix", "display in hex", "show as binary", "use ASCII", "IEEE 754").
- 2. Set `format` (required) using Verdi `wvSetRadix` format names:
- 2.a. "binary"/"bin" -> `format="Bin"`
- 2.b. "octal"/"oct" -> `format="Oct"`
- 2.c. "hexadecimal"/"hex" -> `format="Hex"`
- 2.d. "decimal"/"dec" -> `format="Dec"`
- 2.e. "ASCII" -> `format="ASCII"`
- 2.f. "enum"/"enumerated" -> `format="Enum"`
- 2.g. "IEEE 754"/"floating point"/"float" -> `format="754"`
- 2.h. "IEEE 754 half"/"fp16"/"half precision" -> `format="754_16"`
- 3. Decide whether this is a local-only change with `local_format`:
- 3.a. If the user says "locally", "only this instance/occurrence", or similar, set `local_format=True`.
- 3.b. Otherwise, keep `local_format=False` (default), which applies to all occurrences of that signal in nWave.
- 3.c. Constraint: do not set `local_format=True` when `format` is `"754"` or `"754_16"` (not supported).
- 4. Decide target signals:
- 4.a. If the user provides explicit signal names, set `signal_names=[...]`.
- 4.b. If the user refers to selected signals (e.g., "selected signals", "current selection"), omit `signal_names` so the tool uses the current nWave selection.
- 4.c. If the user says "all signals" (e.g., "set radix to hex on all signals in nWave"), first call `select_all_signals(window=<same window if specified>)` to select all signals in that nWave window, then call `set_radix()` omitting `signal_names` (so it applies to the current selection).
- 4.d. If neither explicit names nor a selection is available, have the user select signals in nWave or provide signal names.
- 5. Decide the nWave window:
- 5.a. If the user specifies a window, set `window` as `$_nWave<#>` (normalize inputs like `nWave:3`, `<nWave:4>`, or `nWave1`).
- 5.b. Otherwise omit `window` so the tool uses the currently active nWave window.
- 6. Signal naming: prefer `/`-delimited signal paths; `wvSetRadix` has limitations around delimiter handling, and some member-signal inputs may fail even after delimiter normalization.
