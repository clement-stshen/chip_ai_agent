---
name: explore_then_find
description: |
  Combined query: first explore design structure, then find specific items matching additional criteria.
target: [design]
examples:
  - "List all signals in <module> and find which ones contain 'data'."
  - "Show instances under <scope> and filter those with 'cpu' in name."
  - "Get all ports of <module> and find the clock-related ones."
  - "List always blocks in <module> and show me the ones with posedge."
---

## Steps
- 1. Perform initial structure exploration by calling `structure_exploration()` with the first part of the query to get the output file.
- 2. Filter the results by calling `grep_files()` with the filter pattern and the output file path.
- 3. Report the filtered results to the user.
