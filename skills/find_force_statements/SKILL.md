---
name: find_force_statements
description: Find force statements in a scope or the entire design.
target: [design]
examples:
  - "How many force statements are used within <instance>?"
  - "Find all force statements in the design."
  - "List force statements in <module>."
---

## Steps
- 1. Search for force statements in the design by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
