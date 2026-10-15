---
name: find_tasks_and_functions
description: Find task/function definitions or task/function calls in the design.
target: [design]
examples:
  - "Find all tasks in <module>."
  - "How many times has task <task_name> been called?"
  - "List all function definitions in the design."
  - "Find function calls in <scope>."
---

## Steps
- 1. Search for task and function definitions or calls by calling `structure_exploration()` with the user's natural language query.
- 2. Report the results to the user.
