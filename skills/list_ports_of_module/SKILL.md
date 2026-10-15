---
name: list_ports_of_module
description: List input/output/inout ports of a module instance or module definition.
target: [design]
examples:
  - "List all input ports of <module>."
  - "What are the output ports of <module_def>?"
  - "Get the input/output port of <module> definition."
  - "Show me all ports of <instance>."
---

## Steps
- 1. Extract port information from the specified module by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
