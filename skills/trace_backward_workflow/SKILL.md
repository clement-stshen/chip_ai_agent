---
name: trace_backward_workflow
description: |
  Find drivers and sources of a signal by tracing upstream connectivity through the design hierarchy.
  Use when user asks about what drives a signal, finding signal sources, or upstream connectivity analysis.
target: [statictrace]
examples:
  - What drives signal X?
  - Find the driver of signal Y
  - Trace backward from signal Z
  - What is the source of signal A?
  - Show me the driver hierarchy of signal B
  - Get all drivers recursively for signal C
  - Multi-level driver trace of signal D
  - Trace cone of influence for signal E
  - Trace the COI of signal F
  - Trace backward to register for signal G
  - Trace backward to register for signal G within the same module
  - Trace backward from signals A, B, C
  - Find drivers of all these signals: signal_X, signal_Y, signal_Z
  - What drives each of these signals: top.cpu.data, top.mem.addr?
  - Trace backward from signals in the previous tool result
---

## Steps
- 1. Parse user query to determine trace parameters: <signal(s)>, <max_trace_level>, <trace_to_sequential>, <stop_on_module_boundary>
- 1.a. If query contains 'direct driver', 'immediate driver': use max_trace_level=1
- 1.b. If query contains 'deep trace', 'complete path', 'multi-level', 'cone', 'all drivers recursively', 'cone of influence(COI)': use max_trace_level=5
- 1.c. Default max_trace_level=1 if no depth context is given
- 1.d. Set trace_to_sequential=True ONLY when user wants to stop at sequential element (register/latch)
       boundaries to find which upstream registers/latches feed into the signal (NOT for normal driver tracing)
- 1.d.1. When trace_to_sequential=True, ALWAYS use max_trace_level=1 (each request stops at the first
       sequential boundary, so only one level is traced per request). Ignore any deeper depth context.
- 1.e. Set stop_on_module_boundary=True ONLY when trace_to_sequential=True AND the user explicitly wants to
       restrict the search to sequential elements within the SAME module/instance boundary (e.g. 'within the
       same module', 'in this instance only', 'without crossing module boundaries'). Default False (the trace
       passes through module boundaries). stop_on_module_boundary is ignored when trace_to_sequential=False.
- 2.a **Single signal**: Call `trace_backward(entries=[<signal>], max_trace_level=<level>, trace_to_sequential=<True/False>, stop_on_module_boundary=<True/False>)`
- 2.b **Multiple signals**: Call `trace_backward(entries=[<signal_A>, <signal_B>, ...], max_trace_level=<level>, trace_to_sequential=<True/False>, stop_on_module_boundary=<True/False>)`
      - Do NOT call the tool multiple times — pass all signals in a single `entries` call.
- 2.c **From prior tool output**: `trace_backward(input_file_path=<path>, max_trace_level=<level>, trace_to_sequential=<True/False>, stop_on_module_boundary=<True/False>)` —
      use when a prior tool produced a framework output file. Signal names are read from the file and traced in batch.
      Mutually exclusive with `entries`.
- 3. **Answer the question** using the following priority (stop as soon as you can answer):
-     a. If the `File Content Preview` summary already answers the question, respond directly.
-     b. If more detail is needed (e.g. specific cells, operation types, signal values at certain depths), 
       use `read_files` or `grep_files` on the `File Path` to read or search the full trace data.
-     b.1. If the question needs module DEFINITION name/type, signal bit-width, port direction, or register/wire type 
       → these are NEVER present in the trace file → go to step c immediately. 
       Do NOT try to use signal path components as module names.
-     b.2. Otherwise, use read_files or grep_files to get more detail from File Path.
-     c. Use `gen_npi_collected_data` ONLY IF the question requires a per-signal attribute 
       NOT visible in the trace text (module DEFINITION name / type, signal bit-width, port direction, register/wire type). 
-     c.1. File path and instance scope are already in the trace text — do NOT call NPI for them. 
-     c.2. Try to answer from the returned NPI file's `collected_data` before proceeding to step d. 
       Read the NPI file path returned by gen_npi_collected_data 
       together with the original trace File Path to get full context.
-     c.3. If both c and d are needed: pass BOTH the original trace `File Path` (as `trace_result_file_path`) 
       AND the npi_collected_data file path (as `npi_collected_data_file_path`) to `analyze_trace_result`.
-     d. For **multi-level** traces (max_trace_level > 1) or **trace_to_sequential=True**: use `analyze_trace_result` 
       ONLY IF steps a–b cannot answer the question, 
       AND the question requires programmatic analysis (filtering by conditions, complex graph traversal). 
-     d.1. You may call d directly without c if no NPI attributes are needed.
-     d.2. CONSTRAINT: if both c and d are needed, c MUST come before d.
-     d.3. Note: `analyze_trace_result` is NOT supported for single-level (max_trace_level=1) traces without trace_to_sequential.
- 4. Format response with driver hierarchy, source locations, and signal paths
- 5. **Multi-signal (batch) result**: Result is a manifest file.
-     a. Read the manifest `File Path` to get the `signal_files` map.
-     b. For each signal, read its per-signal result file (same format as single-signal).
-     c. Report any failed signals from the `errors` field in the manifest.
