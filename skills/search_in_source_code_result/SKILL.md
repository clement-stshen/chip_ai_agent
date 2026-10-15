---
name: search_in_source_code_result
description: Search for specific lines or patterns in a previous get_source_code result.
target: [design]
examples:
  - "In the source code above, find all 'always @' blocks."
  - "From the previous code, show me lines with 'reset'."
  - "Find where <signal> is used in the code."
---

## Steps
- 1. Identify the output file path from the previous source code retrieval operation.
- 2. Search for the specific pattern within the output file by calling `grep_files()` with the pattern and output file path.
- 3. Report the matching lines with line numbers to the user.
