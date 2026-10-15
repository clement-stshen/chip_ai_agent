---
name: trace_active_driver_workflow
description: |
  Trace which drivers actively control a signal's value at a specific simulation time.
  Handles known-value driver analysis with automatic memory write detection and follow-up.
  Supports single-signal and multi-signal (batch) mode.
  When the tool returns recommended_function=trace_x, consult trace_x_workflow for handling.
target: [activetrace]
examples:
  - What caused signal X to change?
  - Trace driver of signal Y at time 100ns
  - Why did Z have this value?
  - Find root cause of signal A
  - Show me what drives signal B at time 50
  - Analyze value change for signal C
  - What is actively driving signal D?
  - Which driver is active for signal E at 200ns?
  - Find the active driver causing signal F value change
  - Trace active drivers for signals A and B at 100ns and 200ns respectively
  - What is driving signals X and Y at time 300ns?
  - Find active drivers for sig1, sig2, sig3 at times 50ns, 100ns, 150ns in one call
  - Trace active drivers for signals in the previous tool result
---

## Steps
- 1. Parse user query to determine trace parameters: <signal(s)>, <time(s)>, <max_trace_level>
- 1.a. **Single vs batch**: Determine whether the user wants to trace one signal or multiple signals.
-     - **Single signal**: Use `entries=[<signal>]` with `times=[<time>]` (omit `times` to use the Verdi cursor time).
-     - **Multiple signals**: Use `entries=[<signal_A>, <signal_B>, ...]` with `times=[<timeA>, <timeB>, ...]` for per-entry times, or omit `times` to use the cursor time for all entries (or set individual `times` elements to null for per-entry cursor time fallback).
- 1.b. Determine the user's depth intent from the query. There are three categories:
-     - **Single-level (max_trace_level=1)**: The user wants only the immediate/direct driver, not the full propagation chain. They are asking about what is directly connected or the next hop only.
-       Examples: "What directly caused...", "Show me the immediate driver of...", "What is driving this signal?", "Trace one level of...", "What directly drives signal X at time Y?"
-     - **Multi-level (max_trace_level=100)**: The user wants to trace through the full propagation chain to find the deepest origin. They are asking about root cause, why something happened, or want to follow the signal path to its source.
-       Examples: "Find root cause of...", "Why did signal X change?", "What caused this value?", "Trace the origin of...", "What is the source of...", "Show the full propagation path", "Trace signal X to its deepest source"
-     - **Default (max_trace_level=1)**: If the intent is ambiguous or no depth preference is expressed, default to single-level.
- 1.c. **Priority rule**: If the query expresses BOTH direct and deep intent (e.g., "What directly caused..."), the direct/single-level intent always wins.
- 2. Call the appropriate form:
- 2.a. **Single signal**: `trace_active_driver(entries=[<signal>], times=[<time>], max_trace_level=<level>)`
- 2.b. **Multiple signals**: `trace_active_driver(entries=[<signal_A>, <signal_B>], times=[<timeA>, <timeB>], max_trace_level=<level>)`
-     - Use `times` to give each signal its own time. Set an individual entry to null to use the Verdi cursor time for that entry. Omit `times` entirely to use the cursor time for all entries.
-     - Do NOT call the tool multiple times for different signals — pass all signals in a single `entries` call.
- 2.c. **From prior tool output**: `trace_active_driver(input_file_path=<path>, max_trace_level=<level>)` — use when
-     - a prior tool produced a framework output file containing a signal list (with optional per-signal times).
-     - Mutually exclusive with `entries`. Omit `max_trace_level` if not specified by user.
- 3. **Redirect check**: If result contains `recommended_function: "trace_x"`, the signal has X-value at the given time. Consult `trace_x_workflow` to handle this case.
- 4. **Answer the question** using the following priority (stop as soon as you can answer):
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
        Read the NPI file path returned by gen_npi_collected_data together with the original trace File Path to get full context.
-     c.3. If both c and d are needed: pass BOTH the original trace `File Path` (as `trace_result_file_path`) 
        AND the npi_collected_data file path (as `npi_collected_data_file_path`) to `analyze_trace_result`.
-     d. Use `analyze_trace_result` ONLY IF steps a–b cannot answer the question, 
        AND the question requires programmatic analysis (filtering by conditions, complex graph traversal). 
-     d.1. You may call d directly without c if no NPI attributes are needed.
-     d.2. CONSTRAINT: if both c and d are needed, c MUST come before d.
- 5. **Multi-signal (batch) result**: The result is a manifest file mapping each signal name to its per-signal result file.
-     a. Read the manifest `File Path` to get the `signal_files` map.
-     b. For each signal, read its per-signal result file (same format as a single-signal result) and answer the question.
-     c. If any signals failed, report them from the `errors` field in the manifest.
- 6. Format response with summary, detailed analysis, and file paths if available
