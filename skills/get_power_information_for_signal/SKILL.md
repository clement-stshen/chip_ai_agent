---
name: get_power_information_for_signal
description: |
  Get power information for an RTL signal or instance, including its power domain and the complete power path (driver chain).
  Use when user asks about power domain of a signal, power supply path, or how a signal is powered.
target: [power]
examples:
  - "What power domain does signal clk belong to?"
  - "How is instance cpu_core powered?"
  - "Get the power path for signal data_out"
  - "Which power domain powers module top/alu?"
  - "Show power supply chain for signal reset_n"
---

## Overview

This skill retrieves power information for an RTL signal or instance by first finding its power domain, then tracing the power path (driver chain) to show the complete power supply hierarchy.

## Steps

1. **Get power domain for the signal/instance**:
   - Call `get_power_domain_by_instance_or_signal(full_name=<signal_or_instance_name>)` to find which power domain the signal/instance belongs to
   - Extract the power domain name from the result (e.g., "PD_TOP", "PD_MEM")
   - If no power domain found, report that the signal is not in any power domain

2. **Trace the power path (driver chain)**:
   - Call `trace_power_object_static_driver(power_object_name=<power_domain_name>)` to get the driver chain
   - This shows the complete power supply hierarchy: which supply nets, supply sets, and power switches feed into this power domain

3. **Present the power information**:
   - Signal/instance name and its power domain
   - Power domain details (primary supply, ground supply)
   - Complete power path from source to the power domain
   - Any intermediate power switches or supply sets in the path

## Result Interpretation

### Example Output
```
Signal: top/cpu/data_out
Power Domain: PD_CPU

Power Path:
  VDD_CORE (supply net)
    -> SS_CORE (supply set)
      -> SW_CPU (power switch)
        -> PD_CPU.primary (supply set handle)
          -> PD_CPU (power domain)

The signal is powered through power switch SW_CPU, which can be controlled to power down the CPU domain.
```

## Notes

- RTL signals inherit power domain from their containing module/instance
- If a signal crosses power domains, isolation strategies may apply
- The power path shows the static power network structure
- Power switches in the path indicate controllable power islands
