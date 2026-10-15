---
name: get_power_object_relationship
description: |
  Find relationships between two power objects by tracing static drivers to find common ancestors.
target: [power]
examples:
  - "Find relationship between PD_TOP and PD_MEM"
  - "What is the common source of VDD1 and VDD2?"
---

## Steps

1. **Handle power switch specially**:
   - If either object is a power switch, first call `report_power_switch(full_name=<switch_name>)` to get its input/output supply nets
   - Use the supply net (e.g., `input_supply_net` or `output_supply_net`) instead of the switch itself for relationship tracing

2. **Call `get_two_power_object_relationship(power_object_1, power_object_2)`**
   - Traces static drivers for each object
   - Finds nearest common ancestor node

3. **Interpret result**:
   - `relationship_type`:
     - `common_source`: Both share a common power source
     - `direct_driver`: One directly drives the other
     - `same_object`: Same power object
     - `no_connection`: No common ancestor (isolated power islands)
   - `common_ancestor`: The shared power source (if any)
   - `path_from_object_1/2`: Paths to common ancestor

## Notes

- Traces **upstream (driver)** direction only
- Default trace depth is 2 levels; use `max_trace_level` for deeper traces
- Local names auto-resolved using current scope
- **Power switches**: Must extract supply nets first via `report_power_switch` before tracing relationship
