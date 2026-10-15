---
name: get_power_information_for_instance
description: |
  Get power information for an object (RTL instance, signal, or power object).
  First identifies whether the object is a power object or HDL element, then retrieves appropriate information.
  Use when user asks about power information for any object with '/' delimiter path.
target: [power]
examples:
  - "What power domain does instance cpu_core belong to?"
  - "How is module top/alu powered?"
  - "Get information for system/SW_FSM"
  - "Show power info for system/PD_TOP"
  - "What is system/iso_ctrl?"
---

## Overview

This skill retrieves power information for any object. It first identifies whether the object is a UPF power object or an HDL element (instance/signal), then calls the appropriate tool.

## Steps

1. **Identify object type FIRST**:
   - Call `identify_object_type(name=<object_name>)` to determine if it's a power object or HDL element
   - The result will indicate:
     - `is_power_object`: True/False
     - `power_object_type`: e.g., npiPwPowerDomain, npiPwPowerSwitch, npiPwIsoStrategy
     - `suggested_tool`: Which tool to use next

2. **If power object** (is_power_object=True):
   - Use the `suggested_tool` from step 1, typically one of:
     - `report_power_domain` for power domains (PD_*)
     - `report_power_switch` for power switches (SW_*, sw_*)
     - `report_isolation_strategy` for isolation strategies (iso_*, ISO_*)
     - `report_retention_strategy` for retention strategies (ret_*, RET_*)
     - `report_supply_net` / `report_supply_set` / `report_supply_port` for supplies

3. **If HDL element** (is_power_object=False):
   - Call `get_power_domain_by_instance_or_signal(full_name=<object_name>)` to find its power domain
   - Extract the power domain name from the result (e.g., "PD_TOP", "PD_MEM")
   - If no power domain found, report that the instance is not in any power domain

4. **Present the power information**:
   - Object type (power object or HDL element)
   - For power objects: detailed report from the appropriate report_* tool
   - For HDL elements: instance name and its power domain

## Result Interpretation

### Example 1: Power Object Query (system/SW_FSM)
```
Object: system/SW_FSM
Type: Power Switch (npiPwPowerSwitch)

Power Switch Info:
  Name: SW_FSM
  Input Supply: system/VDD
  Output Supply: system/SW_FSM.out
  Control Signal: system/sw_ctrl
  ...
```

### Example 2: HDL Instance Query (top/cpu_core)
```
Object: top/cpu_core
Type: HDL Instance

Power Domain: PD_CPU
```

## Notes

- **Always call `identify_object_type` first** to determine the correct tool to use
- Power objects use '/' as hierarchy delimiter (e.g., system/PD_TOP, system/SW_FSM)
- Common power object naming patterns: PD_*, VDD*, VSS*, iso_*, ISO_*, ret_*, RET_*, sw_*, SW_*
- RTL instances belong to the power domain defined in UPF for their scope
