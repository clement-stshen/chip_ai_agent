---
name: multi_pattern_search
description: |
  Try multiple grep patterns when looking for information that could be expressed in different ways.
target: [design]
examples:
  - "Find clock signal (could be clk, clock, CLK, etc.)."
  - "Locate reset logic (could be rst, reset, rstn, etc.)."
  - "Find the enable condition (could be en, enable, valid, etc.)."
---

## Steps
- 1. Try searching with the first likely pattern by calling `grep_files()` with pattern1 and target file(s).
- 2. If not found or insufficient, try an alternative pattern by calling `grep_files()` with pattern2 and target file(s).
- 3. Continue with additional patterns as needed by repeating grep searches.
- 4. Combine and deduplicate results from successful searches.
- 5. Report all findings to the user.
