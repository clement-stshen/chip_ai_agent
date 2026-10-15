---
name: find_assertions
description: Find assertions (assert, assume, cover) in the design.
target: [design]
examples:
  - "Find all assertions in <module>."
  - "List coverage points in the design."
  - "Show me all assume statements in <scope>."
---

## Steps
- 1. Search for assertion statements in the design by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
