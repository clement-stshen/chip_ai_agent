---
name: read_specific_lines
description: |
  Read specific line ranges from a previous output file when user wants to see context around a specific location.
target: [design]
examples:
  - "Show me lines 50-100 of the previous output."
  - "Read the context around line <line_number>."
  - "Show me more details around the match."
---

## Steps
- 1. Identify the output file path from the previous tool operation.
- 2. Read the specified line range by calling `read_files()` with the file path and line range parameters (start_line, end_line).
- 3. Report the content to the user.
