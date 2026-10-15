---
name: iterative_grep_search
description: |
  Iteratively search for information using grep when initial results are insufficient, too large, or don't contain the needed data.
target: [design]
examples:
  - "Find where <signal> is assigned (may need multiple searches)."
  - "Locate the definition of <identifier> in the code."
  - "Find all usages of <pattern> and show context."
---

## Steps
- 1. Perform initial pattern search by calling `grep_files()` with the pattern and target file(s).
- 2. Analyze the results:
- 2.a. If no matches found, try alternative patterns or broader search criteria.
- 2.b. If too many matches, refine the pattern to be more specific.
- 2.c. If result file is too large, narrow down by calling `grep_files()` again with a refined pattern on the result file.
- 3. If needed context is outside visible range, expand the view by calling `read_files()` with appropriate line range parameters.
- 4. Repeat steps 1-3 until the required information is found.
- 5. Report findings to the user.
