---
name: search_in_exploration_result
description: |
  Search for specific items in a previous structure_exploration result when the output is too large or user wants to filter/find specific entries.
target: [design]
examples:
  - "From the previous result, find signals containing 'clk'."
  - "In the list above, which ones have 'error' in the name?"
  - "Filter the previous output to show only input ports."
  - "Find <pattern> in the result."
---

## Steps
- 1. Identify the output file path from the previous structure exploration operation.
- 2. Search for the specific pattern within the output file by calling `grep_files()` with the pattern and output file path.
- 3. Report the filtered results to the user.
