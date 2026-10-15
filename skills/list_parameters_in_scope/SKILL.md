---
name: list_parameters_in_scope
description: List parameters and their values in a module instance or scope.
target: [design]
examples:
  - "What parameters are in module <module>?"
  - "List parameters in scopes whose names contain <pattern>."
  - "Show parameter values of <instance>."
---

## Steps
- 1. Extract parameter information and their values by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
