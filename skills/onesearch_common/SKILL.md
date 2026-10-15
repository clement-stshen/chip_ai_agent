---
name: onesearch_common
description: |
  Shared parameter generation rules for all OneSearch skills.
  This skill MUST be applied together with any of the following skills:
    - search_db
    - search_gui_content
    - search_menu_command
  When any of the above skills is selected, the rules in this file are MANDATORY
  and take precedence over any conflicting instructions in those individual skills.
target: [onesearch]
examples:
  - "Using onesearch to find clock"
  - "Find which windows contain clock"
  - "Search for windows with signal"
  - "Search docs for dock*"
  - "Find menu for trace"
---

## Scope

The rules below apply to **all** OneSearch tool calls, regardless of which specific skill (`search_db`, `search_gui_content`, or `search_menu_command`) is being used. Always consult this file **in addition to** the individual skill file.

## Parameter Generation Rules (MANDATORY)

- **Default by Omission**: If the user does NOT explicitly request a capability, DO NOT pass the corresponding parameter. Default behavior MUST be represented by omitting parameters, NOT by passing default values.
- **Trigger-Based**: A parameter MAY appear ONLY if the user query contains an explicit trigger phrase.
- **Mutually Exclusive**: `use_regex`, `use_wildcard`, and `find_whole_words_only` are MUTUALLY EXCLUSIVE. When one is `True`, OMIT the other two entirely (do NOT pass them as `False`).
- **No Empty/Null Values**: Do NOT pass `report_file=""` or `match_case=None` or `max_results=None`. Omit the parameter entirely.
- **Conflict Resolution**: If the user provides conflicting instructions, apply the last, clearest instruction. If ambiguity remains, ask for clarification.
- **Skill-Specific Parameters**: Different skills may use different parameter names for similar concepts. Do NOT copy parameters across skills by analogy (e.g., `use_regex` in GUI vs. `use_wildcard=False` in DB).
- **User-Specified Paths** (`search_db` only): If the user names a CONCRETE path in the query, route it by KIND: individual file(s) (e.g. "my documentation is at /docs/spec.docx", "search /p/a.sv and /p/b.sv") → `user_specified_files`; a FILELIST file whose lines are the files to search (`.lst`/`.f`/`.list`, e.g. "search the files listed in /p/docs.lst") → `user_specified_filelists`; a directory (e.g. "look under /proj/rtl") → `user_specified_dirs`. ALSO set `search_engine_name` to the engine matching that path's content (documentation `.pdf`/`.docx`/`.txt`/`.md` → `Docs`; source/RTL → `Sources`; `.log`/`.rpt` → `Logs`). When set, that engine searches ONLY the named inputs. Do NOT populate these for generic queries that name no path. If a named path does not exist, the tool reports it back instead of silently ignoring it.

## Multi-Keyword Search Recognition (MANDATORY)

When the user query contains **multiple search terms** connected by natural language conjunctions, you MUST construct the `key_word` accordingly. Recognize the following patterns:

- **OR**: "A or B", "A or B or C", "either A or B"
- **AND**: "A and B", "both A and B", "A as well as B"
- **NOT**: "A but not B", "A excluding B", "A without B"
- **Combined**: "A and B but not C", "A or B excluding C"

The exact `key_word` syntax for combining multiple keywords **differs by tool and matching mode**. Refer to each tool's skill file (`search_db`, `search_gui_content`, `search_menu_command`) for the correct format.

**Key differences**:
- `onesearch_search_db` in **wildcard mode**: OR uses `||` (double pipe, no spaces), e.g. `key_word='A||B'`
- `onesearch_search_db` in **regex mode**: OR uses `|` (single pipe), e.g. `key_word='A|B'`
- `onesearch_search_gui_content` in **default partial-match mode**: OR uses `||` with spaces, e.g. `key_word='A || B'`
- `onesearch_search_menu_command`: No multi-keyword support in a single call. Plan multiple separate calls instead.
