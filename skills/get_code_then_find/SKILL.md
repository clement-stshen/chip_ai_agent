---
name: get_code_then_find
description: |
  Combined query: first get source code, then find specific patterns or lines.
target: [design]
examples:
  - "Show me the source code of <module> and find all case statements."
  - "Get RTL of <module> and find where <signal> is assigned."
  - "Print code of <module> and show lines with 'posedge clk'."
---

## Steps
- 1. Retrieve the source code by calling `get_code_by_module_instance()` or `get_code_by_module_definition()` depending on whether instance or definition is provided.
- 2. Search for the specific pattern by calling `grep_files()` with the pattern and output file path.
- 3. Report the matching lines to the user.
