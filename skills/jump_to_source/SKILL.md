---
name: jump_to_source
description: |
  Navigate to a specific source code location in the nTrace window. Can open files and jump to specific lines or line ranges.
target: [design]
examples:
  - "Open file <path> at line <N>."
  - "Jump to line <N> in <file>."
  - "Show file <path> lines <M> to <N>."
  - "Go to line <N> in the current file."
  - "Open <file> in a new tab at line <N>."
  - "Jump to source at <file>:<line>."
  - "Navigate to line <N>."
---

## Steps
- 1. Determine if the user wants to open a specific file or navigate within the current file.
- 2. If opening a specific file:
-    - Call `jump_to_source()` with file_path parameter set to the absolute file path.
-    - If a specific line is mentioned, include the line parameter.
-    - If a range is mentioned (e.g., 'lines 10 to 20'), include both range_start and range_end parameters.
-    - If user wants a new tab, set show_in_new_tab to True (default is False).
- 3. If navigating within the current file:
-    - Call `jump_to_source()` with only the line parameter (file_path should be None).
- 4. Report the navigation action to the user.
- 5. Note: Range highlighting only works when file_path is provided.
