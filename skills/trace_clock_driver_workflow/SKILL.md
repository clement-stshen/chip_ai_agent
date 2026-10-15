---
name: trace_clock_driver_workflow
description: |
  Identify which drivers of a signal are clock type.
  Use when user asks about clock sources, clock identification, or clock signals driving a specific signal.
target: [statictrace]
examples:
  - What clock drives signal X?
  - Find clock of signal Y
  - Identify clock source of signal Z
  - Is signal A driven by a clock?
  - Show clock drivers of signal B
  - What clock drives signals A and B?
  - Find clock of signals X, Y, Z
  - Identify clock drivers for all these signals: top.clk1, top.clk2
  - Find clock drivers for signals in the previous tool result
---

## Steps
- 1. Parse user query to determine: <signal(s)>
- 2.a. **Single signal**: Call `trace_clock_driver(entries=[<signal>])`
- 2.b. **Multiple signals**: Call `trace_clock_driver(entries=[<signal_A>, <signal_B>, ...])`
       - Do NOT call the tool multiple times — pass all signals in a single `entries` call.
- 2.c. **From prior tool output**: `trace_clock_driver(input_file_path=<path>)` — use when a prior tool produced a
       framework output file. Mutually exclusive with `entries`.
- 3. Present results:
- 3.a. List all clock-type drivers found for the signal
- 3.b. If no clock drivers found, inform user
- 4. Format response with clock signal names and their source locations
- 5. **Multi-signal (batch) result**: Result is a manifest file.
-    a. Read the manifest `File Path` to get the `signal_files` map.
-    b. For each signal, read its per-signal result file and list clock-type drivers.
-    c. Report any failed signals from the `errors` field in the manifest.
