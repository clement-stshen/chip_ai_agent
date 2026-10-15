---
name: trace_active_memory_workflow
description: |
  Trace memory write operations for memory arrays and register files.
  The user explicitly mentions "memory", "register file", "mem", "RAM", "ROM",
  or refers to a signal that is clearly a memory array with an index (e.g., mem[5], register_file[3]).
  When the result indicates the signal is not a memory net, consult trace_active_driver_workflow as fallback.
  Supports single-element and multi-element (batch) mode via the same entries+times interface.
target: [activetrace]
examples:
  - What caused memory mem at index 5 to change at 100ns?
  - Trace memory write to register_file[3] at time 200
  - Why did memory array A change value?
  - Find the write operation for memory B at index 10
  - What wrote to mem[7] at time 50ns?
  - Trace memory writes for mem[5] at 100ns and mem[10] at 200ns
  - What caused mem[2] and mem[8] to change at time 300ns?
  - Find write operations for register_file[0], register_file[1], and register_file[2] at 500ns
---

## Steps
- 1. Parse user query to determine trace parameters: <memory_signal(s)>, <index/indices>, <time(s)>
- 1.a. Extract memory array name(s) (hierarchical signal name)
- 1.b. Extract array index/indices (zero-based integer) to construct `"signal[index]"` entry strings
- 1.c. Extract time value(s) (with optional unit); omit or set to null for Verdi cursor time
- 2. Call `trace_active_memory` using `entries` + `times`:
-     - Always use `entries=["signal[index]", ...]` and `times=["time", ...]` (or `times=[null, ...]` for cursor time).
-     - Single element: `trace_active_memory(entries=["top.cpu.mem[5]"], times=["100ns"])`
-     - Multiple elements: `trace_active_memory(entries=["top.cpu.mem[5]", "top.cpu.mem[10]"], times=["100ns", "200ns"])`
-     - Do NOT call the tool multiple times — pass all elements in a single call.
- 3. **Redirect check**: If result indicates the signal is not a memory net, consult `trace_active_driver_workflow` to handle this case.
- 4. **Single-element result**: Present results:
- 4.a. Show the write operation that caused the value change
- 4.b. Include the time when the write occurred
- 4.c. Show the write data value and source
- 5. **Multi-element (batch) result**: The result is a manifest file mapping each `"signal[index]"` key to its per-element result file.
-     a. Read the manifest `File Path` to get the `signal_files` map.
-     b. For each element, read its per-element result file (same format as a single-element result) and present the findings.
-     c. Report any failed elements from the `errors` field in the manifest.
- 6. Format response with summary of memory write operation details
