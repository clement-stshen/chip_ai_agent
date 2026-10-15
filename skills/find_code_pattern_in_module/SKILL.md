---
name: find_code_pattern_in_module
description: |
  Find specific code patterns, syntax, or text within a module's source code. Use this when looking for specific coding style, comments, assign statements, or patterns that NPI doesn't directly support.
target: [design]
examples:
  - "Find all assign statements in module <module>."
  - "Show me all comments in <module>."
  - "Find lines containing '<pattern>' in module <module>."
  - "How is signal <signal> assigned in <module>?"
  - "Show me the sensitivity list of always blocks in <module>."
  - "Find all `ifdef in <module>."
---

## Steps
- 1. Retrieve the source code file by calling `get_code_by_module_instance()` or `get_code_by_module_definition()` depending on whether instance or definition name is provided.
- 2. Search for the specific pattern within the output file by calling `grep_files()` with the pattern and output file path.
- 3. Report the matching lines to the user.
