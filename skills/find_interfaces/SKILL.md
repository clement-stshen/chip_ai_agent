---
name: find_interfaces
description: Find interface instances or interface bindings in the design.
target: [design]
examples:
  - "Find all SI interface bindings with <interface_def>."
  - "List all interfaces in the design."
  - "What interfaces are instantiated in <module>?"
---

## Steps
- 1. Search for interface instances and bindings by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
