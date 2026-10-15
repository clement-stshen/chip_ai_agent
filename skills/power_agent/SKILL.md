---
name: power_agent
description: |
  Query and analyze UPF (Unified Power Format) power objects in the design including power domains, supply sets, supply nets, supply ports, power switches, isolation strategies, retention strategies, and power state tables. Note: Power object tracing is not supported by this skill.
target: [design]
examples:
  - "What power domains are in the design?"
  - "Get the power domain for instance <instance>."
  - "Show the supply sets under scope <scope>."
  - "What is the isolation strategy for <domain>?"
  - "Report the retention strategy for <domain>."
  - "Show the power state table for <pst>."
  - "What is the status of power object <object> at time <time>?"
  - "Get the power switch information for <switch>."
  - "Show the supply net details for <net>."
  - "What power rules apply to signal <signal>?"
---

## Steps
- 1. Pass the user's query to `power_agent()` tool which delegates to the specialized Power Agent for UPF analysis.
- 2. The Power Agent will internally determine which power tool to use based on the query:
  - `get_power_top()` - Get the top-level scope of the power design
  - `get_power_objects_by_scope()` - Get power objects under a specific scope
  - `get_power_domain_by_instance_or_signal()` - Get power domain for an HDL instance/signal
  - `query_signal_power_rule()` - Query power rules for a signal
  - `report_power_domain()` - Detailed power domain information
  - `report_supply_set()` - Detailed supply set information
  - `report_supply_net()` - Detailed supply net information
  - `report_supply_port()` - Detailed supply port information
  - `report_port_state()` - Port state details
  - `report_power_state()` - Power state details
  - `report_power_state_table()` - Power state table information
  - `report_isolation_strategy()` - Isolation strategy details
  - `report_retention_strategy()` - Retention strategy details
  - `report_power_switch()` - Power switch information
  - `get_power_object_status()` - Power object status at specific time
  - `structure_exploration()` - General UPF structure traversal
- 3. Return the results to the user.
