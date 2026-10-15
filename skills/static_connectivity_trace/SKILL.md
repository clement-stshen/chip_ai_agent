---
name: static_connectivity_trace
description: |
  Trace signal connectivity through the design structure without simulation. Use for finding drivers, loads, clock sources, connectivity paths, or structural relationships in the design.
target: [design]
examples:
  - "What drives signal <signal_name>?"
  - "Find the driver of <signal>."
  - "Trace backward from <signal>."
  - "What loads signal <signal_name>?"
  - "Where does signal <signal> go?"
  - "Trace forward from <signal>."
  - "Trace load of <signal> at time <time>."
  - "What loads <signal> at time <time>?"
  - "Find loads of <signal> at <time>."
  - "Show connectivity of signal <signal>."
  - "Get both drivers and loads for <signal>."
  - "Find path between signal <signal_a> and <signal_b>."
  - "How are <signal_x> and <signal_y> connected?"
  - "Get all drivers recursively for <signal>."
  - "Multi-level driver trace of <signal>."
  - "Trace driver of <signal> until module <module>."
  - "List all paths from <signal> to registers."
  - "What clock drives <signal>?"
  - "Find clock of <signal>."
---

## Steps
- 1. IMPORTANT: Pass the COMPLETE, UNMODIFIED user prompt to `static_trace_tool(<user_prompt>)`.
- 2. The static_trace_tool will internally handle all trace planning, parameter extraction, and execution.
- 3. DO NOT extract signal names, trace levels, or stopping criteria yourself.
- 4. DO NOT decompose the prompt or modify it in any way.
- 5. Return the complete trace results to the user.
