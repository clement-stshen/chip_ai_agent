---
name: trace_chain_driver_workflow
description: |
  Follow a chain of single-input/single-output drivers backward from a signal until a terminal source or branch point.
  Use ONLY when user explicitly mentions 'chain driver' or 'chain-driver' keyword.
target: [statictrace]
examples:
  - Trace chain driver of signal X
  - Follow the chain-driver path from signal Y
  - Show chain driver for signal Z
  - Trace chain driver of signals A and B
  - Follow the chain-driver path from signals X, Y, Z
  - Trace chain driver for signals in the previous tool result
---

## Steps
- 1. Verify user explicitly mentioned 'chain driver' or 'chain-driver' keyword
- 2. Parse user query to determine: <signal(s)>
- 3.a. **Single signal**: Call `trace_chain_driver(entries=[<signal>])`
- 3.b. **Multiple signals**: Call `trace_chain_driver(entries=[<signal_A>, <signal_B>, ...])`
       - Do NOT call the tool multiple times — pass all signals in a single `entries` call.
- 3.c. **From prior tool output**: `trace_chain_driver(input_file_path=<path>)` — use when a prior tool produced a
       framework output file. Mutually exclusive with `entries`.
- 4. Present the chain of connected drivers from the signal to the terminal source
- 4.a. Show each driver in the chain with its location
- 4.b. Indicate where the chain terminates (primary input, multiple drivers, etc.)
- 5. **Multi-signal (batch) result**: Result is a manifest file.
-    a. Read the manifest `File Path` to get the `signal_files` map.
-    b. For each signal, read its per-signal result file and present the driver chain.
-    c. Report any failed signals from the `errors` field in the manifest.
