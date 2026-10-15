---
name: show_hierarchy_tree
description: Show the hierarchical scope tree view of the design or a specific scope.
target: [design]
examples:
  - "Show me the hierarchical scope tree view of the design."
  - "Can you show the hierarchy tree?"
  - "Display the design hierarchy."
  - "Dump the hierarchy tree from <scope>."
---

## Steps
- 1. Generate hierarchical scope tree structure by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
