---
name: trace_connectivity_workflow
description: |
  Find both drivers and loads of a signal in a single bidirectional analysis.
  Performs single-level trace showing both upstream (driver) and downstream (load) connections.
  Use when user wants complete connectivity picture of a signal.
target: [statictrace]
examples:
  - Show connectivity of signal X
  - Get both drivers and loads for signal Y
  - What is connected to signal Z?
  - Trace connectivity of signal A
  - Show all connections of signal B
  - Show connectivity of signals A, B, and C
  - Get both drivers and loads for signals X and Y
  - What is connected to each of these signals: top.cpu.data, top.mem.addr?
  - Show connectivity for signals in the previous tool result
---

## Steps
- 1. Parse user query to determine trace parameters: <signal(s)>
- 2.a. **Single signal**: Call `trace_connectivity(entries=[<signal>])`
- 2.b. **Multiple signals**: Call `trace_connectivity(entries=[<signal_A>, <signal_B>, ...])`
       - Do NOT call the tool multiple times — pass all signals in a single `entries` call.
- 2.c. **From prior tool output**: `trace_connectivity(input_file_path=<path>)` — use when a prior tool produced a
       framework output file. Signal names are read from the file and analyzed in batch.
       Mutually exclusive with `entries`.
- 3. **Answer the question** using the following priority:
-     a. If the `File Content Preview` summary already answers the question, respond directly.
-     b. If more detail is needed, use `read_files` or `grep_files` on the `File Path` to read
       or search the full trace data.
-     Note: `analyze_trace_result` is NOT supported for connectivity traces.
- 4. Present results with two separate sections:
- 4.a. DRIVER section: upstream connections driving the signal
- 4.b. LOAD section: downstream connections reading the signal
- 5. Format response clearly separating driver and load information
- 6. **Multi-signal (batch) result**: Result is a manifest file.
-    a. Read the manifest `File Path` to get the `signal_files` map.
-    b. For each signal, read its per-signal result file (same format as single-signal).
-    c. Report any failed signals from the `errors` field in the manifest.
-    d. Present driver and load sections separately for each signal.
