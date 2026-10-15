---
name: find_case_statements
description: |
  Find case statements in the design, optionally checking for missing default branches.
target: [design]
examples:
  - "Please check which case doesn't include default branch."
  - "Find all case statements in <module>."
  - "List case statements without default in the design."
---

## Steps
- 1. Search for case statements and check their default branches by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
