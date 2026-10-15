---
name: trace_two_point_workflow
description: |
  Find the path between two specific signals in the design.
  Traces connectivity from a source signal to a destination signal, showing the shortest path and intermediate connections.
  Use when user asks about how two signals are connected or wants to find a path between two points.
  Supports single-pair and multi-pair (batch) mode.
target: [statictrace]
examples:
  - Find path between signal A and signal B
  - How are signal X and signal Y connected?
  - Trace from signal_src to signal_dst
  - Is there a connection between signal A and signal B?
  - Show the path from clock to data_out
  - Find paths from A to B, from C to D, and from E to F
  - Trace two-point connectivity for these pairs: from src1 to dst1, from src2 to dst2
---

## Steps
- 1. Parse user query to determine: <from_signal(s)>, <to_signal(s)>, <flip_flop_handling>, <stop_on_tristate>, <show_neighbor_cells>
- 1.a. Identify the signal pair(s) from the query
- 1.b. **Determine signal-flow direction** (applies to each pair):
       `src_signal_name` is the upstream **from** signal (where the path starts).
       `dest_signal_name` is the downstream **to** signal (where the path ends).
       Use the first matching rule below — do not ask for clarification if a rule applies:
       - User says **"from A"** or **"to B"**: from=A, to=B. No clarification needed.
       - User says **"A is driven by B"** / **"B drives A"**: from=B, to=A.
       - User provides **no directional keyword** (e.g. "how are A and B connected?"): direction is ambiguous; see step 1.e.
- 1.c. Determine flip-flop handling if mentioned (default: `pass_through_flip_flop`);
       set `stop_on_flip_flop` when user wants to stop at registers, `stop_on_flip_flop_except_data_port` only when explicitly stated
- 1.d. Determine tristate handling if mentioned (default: continue through); set `stop_on_tristate=True` only when user wants to stop at tristate buffers
- 1.e. **Direction is ambiguous** only when the user provides no directional keyword (no from/to, no drives/driven-by).
       Do NOT call trace_two_point. Instead, return a suggestion to the caller:
       - State that the direction between the two signals is ambiguous
       - Suggest the caller confirm with the user which signal drives which
       - If the user cannot clarify, suggest calling trace_two_point twice with each direction:
         once with from=A to=B, and once with from=B to=A
       - Note that wrong direction may cause long trace times in large designs
- 1.f. Set `show_neighbor_cells=True` only when user explicitly asks to see neighboring cells around the traced path (default: False)
- 2. **Single pair vs batch**:
- 2.a. **Single pair**: Call `trace_two_point(entries=["<from_signal>-><to_signal>"], flip_flop_handling=<handling>, stop_on_tristate=<True/False>, show_neighbor_cells=<True/False>)`
- 2.b. **Multiple pairs**: Call `trace_two_point(entries=["<from1>-><to1>", "<from2>-><to2>", ...], flip_flop_handling=<handling>, stop_on_tristate=<True/False>, show_neighbor_cells=<True/False>)`
       - Each entry uses `"<from_signal>-><to_signal>"` format (e.g. `"top.cpu.clk->top.mem.clk_in"`),
         where `->` denotes the from-to direction.
       - Do NOT call the tool multiple times — pass all pairs in a single `entries` call.
- 3. **Answer the question** using the following priority:
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
- 4. If no path found, inform user the signals are not connected
- 5. **Multi-pair (batch) result**: Result is a manifest file.
-    a. Read the manifest `File Path` to get the `signal_files` map (keys are `"<from> -> <to>"` strings).
-    b. For each pair, read its per-pair result file (same format as single-pair result) and present the path.
-    c. Report any failed pairs from the `errors` field in the manifest.
