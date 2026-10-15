---
name: find_always_blocks
description: Find always blocks in a module or scope, optionally the N-th always block.
target: [design]
examples:
  - "Find all always blocks in <module>."
  - "What is the first always block in <module>?"
  - "Show me the second always block in <instance>."
  - "List always blocks in the design."
---

## Steps
- 1. Search for always blocks in the design structure by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
