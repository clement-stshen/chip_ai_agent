---
name: trace_x_workflow
description: |
  Trace sources of unknown (X) values for one or more signals or scopes, optionally at specific simulation times.
  Uses XRCA (X-value Root Cause Analysis) engine to identify where X-values originate and how they propagate through the design.
  Supports batch/multi-signal X debugging via XRCA. Trigger on "XRCA", "run XRCA", "X root cause", "trace X", "unknown value", or "why is signal X unknown".
  When the result contains non_x_entries, those signals do not have X at the specified time — suggest trace_active_driver for them instead.
target: [activetrace]
examples:
  - Trace X-value in signal X
  - Why is signal Y unknown?
  - Find the source of X in signal Z
  - Debug X propagation in signal A
  - Why did signal B become X at time 100?
  - What is the source of unknown value in signal C?
  - Signal D has X value, what caused it?
  - Run XRCA on signal E
  - XRCA on signals A, B, C at time 100ns
  - Run XRCA on the previous tool result
---

## Steps
- 1. Parse user query to determine trace parameters: <signal_or_scope>, <time>, and optionally <cause_count>
- 1.a. **Signal vs scope**: A signal (e.g., `top.cpu.data`) is point-checked at the given time. A scope (e.g., `top.cpu`) expands to all child signals and range-scans up to the given time. Use a signal when you know the exact time; use a scope to discover the first X transition (from nonX to X) for all child signals under the scope(1 level only, no recursion).
- 1.b. **Time handling**:
-     - If the user specifies a time, pass it in `times`. With a signal entry this is a point check; with a scope entry this is a range scan from simulation start+1 to the given time to find the first X transition.
-     - If no time is given, omit `times` — the engine scans from simulation start+1 to end of simulation for the first X transition (the +1 offset skips initialization noise).
- 1.c. **cause_count handling**: If the user specifies a maximum number of root causes (e.g., "find top 5 root causes"), capture it as `cause_count` (must be >= 0; 0 means no limit). If not specified, omit it and the engine uses its default.
- 2. Call the appropriate form:
- 2.a **Direct input**: `trace_x(entries=[<signal_or_scope>], times=[<time>], cause_count=<N>)` — omit `cause_count` if not specified by user.
- 2.b **From prior tool output**: `trace_x(input_file_path=<path>, cause_count=<N>)` — use when a prior tool produced a framework output file containing a signal list. Mutually exclusive with `entries`. Omit `cause_count` if not specified.
- 3. Analyze `trace_x` results:
- 3.a **Non-X entries**: If the result contains `non_x_entries`, those signals/scopes do not have X values at the given time. Inform the user and suggest using `trace_active_driver` for those signals.
- 3.b **Invalid entries**: If the result contains `invalid_entries`, inform the user that those signals/scopes were not found in the design.
- 3.c Present X-trace results:
- 3.c.i Show root causes of X-values with signal hierarchy paths
- 3.c.ii Include hints for debugging the X-value issue
- 4. Format response with summary and recommendations for fixing X-value sources
