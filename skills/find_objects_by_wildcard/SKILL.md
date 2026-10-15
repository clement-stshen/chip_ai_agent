---
name: find_objects_by_wildcard
description: Find instances or signals matching wildcard or regex patterns.
target: [design]
examples:
  - "Find all instances whose name starts with n* and instantiated from module <module_def>."
  - "List signals matching pattern *clk* in <scope>."
  - "Find instances with definition name matching *ALU*."
  - "What signals are present in scopes whose full names contain <pattern>?"
---

## Steps
- 1. Search for design objects matching wildcard or pattern criteria by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
