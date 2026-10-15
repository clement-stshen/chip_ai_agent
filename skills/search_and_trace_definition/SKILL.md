---
name: search_and_trace_definition
description: Find a reference and trace back to its definition by iterative searching.
target: [design]
examples:
  - "Find where <signal> is declared."
  - "Locate the definition of parameter <param>."
  - "Find where type <typedef> is defined."
---

## Steps
- 1. Search for all occurrences of the identifier by calling `grep_files()` with the identifier and target file(s).
- 2. Look for declaration patterns (e.g., 'wire <name>', 'reg <name>', 'parameter <name>') in the search results.
- 3. If declaration not in visible results, read the beginning of the module/scope by calling `read_files()` with appropriate line range.
- 4. If identifier is from another module, retrieve and search in that module's code by calling appropriate tools.
- 5. Report the definition location and content.
