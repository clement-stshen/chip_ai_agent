---
name: grep_with_context_expansion
description: |
  When grep finds a match but more context is needed, expand the view by reading surrounding lines.
target: [design]
examples:
  - "Show me the full always block containing <pattern>."
  - "Find <pattern> and show the complete statement."
  - "Locate <signal> assignment and show surrounding logic."
---

## Steps
- 1. Search for initial matches with line numbers by calling `grep_files()` with the pattern and target file(s).
- 2. For each match that needs more context, expand the view by calling `read_files()` with the file path and expanded line range (e.g., match_line-N to match_line+M).
- 3. If the expanded view still doesn't show complete structure, further expand the line range by calling `read_files()` again.
- 4. Report the complete context to the user.
