---
name: list_instances_in_hierarchy
description: |
  List module instances in a scope or the entire design.
  By default, lists only direct child instances of a scope.
  Use "recursively", "hierarchy", or "all levels" to include all descendant instances.
target: [design]
examples:
  - "How many instances are there in the design?"
  - "What are the instances in <scope>?"
  - "List all instances of module <module_def>."
  - "Find instances whose name contains 'ALU'."
  - "Which instances have 'CU' in their hierarchical names?"
  - "What are the full hierarchical instance names of modules that contain the keyword <keyword>?"
  - "List all instances under <scope> recursively."
---

## Scope Behavior
- **"instances in <scope>"** without recursive keywords → direct child instances only
- **"instances under <scope>"** with "recursively/all levels/hierarchy" → all descendant instances
- **"instances in the design"** → typically implies whole design search

## Steps
- 1. Call `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
