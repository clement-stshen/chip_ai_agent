---
name: count_design_objects
description: |
  Count design objects (signals, instances, ports, etc.) in a scope or the entire design.
  By default, counts objects directly in the specified scope.
  Use "recursively" or "entire hierarchy" to count across all descendant scopes.
target: [design]
examples:
  - "How many signals are in <module>?"
  - "Count the instances in the design."
  - "How many input ports does <module> have?"
  - "Count always blocks in <scope>."
  - "Count all flip-flops under <scope> recursively."
---

## Scope Behavior
- **"in <scope>"** without recursive keywords → count objects directly in that scope
- **"under <scope>"** or **"in the design"** with recursive keywords → count across all descendants

## Steps
- 1. Call `structure_exploration()` with the user's natural language query.
- 2. Report the count results to the user.
