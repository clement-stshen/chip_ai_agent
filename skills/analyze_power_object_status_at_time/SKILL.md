---
name: analyze_power_object_status_at_time
description: |
  Analyze why a power object has a specific status at a given time by tracing its active driver.
  Use when user asks why a power domain/supply is ON/OFF, what controls a power object at a time,
  or needs to debug power state issues at a specific simulation time.
target: [power]
examples:
  - "Why is PD_CPU OFF at 100ns?"
  - "What is controlling VDD at time 500ns?"
  - "Analyze why power domain PD_MEM is powered down at 1000ns"
  - "Debug power state of supply net VSS at current time"
  - "What caused power switch SW_TOP to turn off at 200ns?"
---

## Steps

1. **Get power object status at the specified time**:
   - Call `get_power_object_status(full_name=<power_object_name>, time=<time>)` to get the current status
   - Note the power state (ON/OFF), voltage value, and any relevant state information

2. **Trace the active driver at that time**:
   - Call `trace_power_object_active_driver(power_object_name=<power_object_name>, time=<time>)` to find what is actively driving/controlling the power object
   - This reveals the active driver chain that determines the current state

3. **Present the driver path clearly**:
   - Show the complete driver path from root source to the queried power object
   - Format: `source -> intermediate1 -> intermediate2 -> ... -> target`
   - Include state/value at each node in the path

4. **Analyze the results and provide recommendations**:
   - Explain WHY the power object has its current status based on the active driver chain
   - Identify the root cause (e.g., power switch control signal, supply net state)
   - Suggest what to trace next for further debugging:
     - If controlled by a power switch → trace the switch's control signal
     - If controlled by a supply net → trace that supply net's driver
     - If in a power state transition → check the power state table
