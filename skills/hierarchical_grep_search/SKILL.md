---
name: hierarchical_grep_search
description: |
  Search in a hierarchical manner: first grep in a large file, then grep within results, then read specific sections.
target: [design]
examples:
  - "In the large output file, find entries related to <topic>, then show details of <specific_item>."
  - "Search for <broad_pattern> first, then narrow down to <specific_pattern>."
---

## Steps
- 1. Perform initial broad filtering by calling `grep_files()` with a broad pattern on the large file.
- 2. If result is still large, narrow down by calling `grep_files()` with a more specific pattern on the result file.
- 3. Read specific sections of interest by calling `read_files()` with appropriate line range parameters.
- 4. Repeat narrowing as needed until the specific information is found.
- 5. Report findings to the user.
