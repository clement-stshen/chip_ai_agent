---
name: list_signals_in_scope
description: |
  List signals (nets and variables) in a specific scope.
  By default, lists signals directly in the scope (not in child instances).
  Use "recursively" or "to leaf" keywords to include signals in all descendant scopes.
target: [design]
examples:
  - "List all signals in module <module_name>."
  - "What signals are in the scope <scope>?"
  - "Show me input signals in <module>."
  - "Find all output signals in <instance>."
  - "List signals with width and full path in the design."
  - "What signals are present in the module instance <instance>?"
  - "List all signals under <scope> recursively."
---

## Scope Behavior
- **"in <scope>"** without recursive keywords → signals directly in that scope (single-level)
- **"under <scope>"** with keywords like "recursively", "to leaf", "entire hierarchy" → all descendant signals

## Steps
- 1. Call `structure_exploration()` with the user's natural language query.
- 2. The scope behavior is determined by keywords in the query:
  - Default (no recursive keywords): single-level access
  - With "recursively/to leaf/entire/deep": full hierarchy traversal
- 3. Report the results to the user.
