---
name: active_temporal_trace
description: |
  Trace signal driver behavior during simulation to find what actively drives a signal, causes value changes, X-propagation, transitions and memory operations at specific times. Requires waveform data. Use ONLY for driver/fanin tracing with temporal context (time references like 'at time 25', 'at 100ns', 'during time 10'). DO NOT use for load/fanout tracing even when time is specified - load tracing always uses static_connectivity_trace regardless of temporal context.
target: [design]
examples:
  - "What is actively driving signal <signal>?"
  - "Which driver is active for signal <signal> at <time>?"
  - "What is the driver of <signal> at time <time>?"
  - "Find the driver of <signal> trace at time <time>."
  - "Trace driver of <signal> at time <time>."
  - "What drives <signal> at <time>?"
  - "Trace <N> level driver at time <time>."
  - "What caused signal <signal> to change?"
  - "Why did signal <signal> transition?"
  - "Trace X-value in signal <signal>."
  - "Find the root cause of X in <signal>."
  - "What's the source of unknown value in <signal>?"
  - "Trace active driver of <signal> at time <time>."
  - "What caused memory <mem> at index <idx> to change at <time>?"
  - "Trace memory write to <mem>[<idx>] at <time>."
  - "Why did <signal> become X at <time>?"
  - "Find the active driver causing <signal> value change."
  - "Trace the root cause of <signal> transition at <time>."
---

## Steps
- 0. CRITICAL: This skill is ONLY for driver/fanin tracing. If the user asks to trace load/fanout (e.g., "trace the load of signal X"), do NOT use this skill even if time is specified. Use static_connectivity_trace instead.
- 1. IMPORTANT: Pass the COMPLETE, UNMODIFIED user prompt to `active_trace_tool(<user_prompt>)`.
- 2. The active_trace_tool will internally handle all trace planning, parameter extraction, and execution.
- 3. DO NOT extract signal names, time values, or stopping criteria yourself.
- 4. DO NOT decompose the prompt or modify it in any way.
- 5. Return the complete trace results to the user.
