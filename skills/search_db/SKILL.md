---
name: search_db
description: |
  Search across OneSearch databases (Sources, Identifiers, Docs, Logs)
  using wildcard or regular expression patterns, with optional blocking
  and result limits.
target: [onesearch]
examples:
  - "Using onesearch to find clock"
  - "Search docs for dock*"
  - "Search sources for getenv"
  - "OneSearch find En_C.* using regex"
  - "Search identifiers for SearchEngine"
  - "Search docs for dock*, show 10 results"
---

## Input Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `key_word` | `str` | *(required)* | The keyword or pattern to search for. |
| `search_engine_name` | `str` | `"All"` | Search engine scope: `'All'`, `'Sources'`, `'Identifiers'`, `'Docs'`, `'Logs'`. Trigger words in the query (singular, plural, and `"<word> file/files"` variants all count): `source`/`sources`/`source file`/`source files`/`src file`/`src files` → `Sources`; `log`/`logs`/`log file`/`log files` → `Logs`; `doc`/`docs`/`document`/`documents`/`documentation` → `Docs`; `identifier`/`identifiers` → `Identifiers`. If no trigger word appears, OMIT this argument (defaults to `All`). |
| `search_limit` | `int` | `1000` | Maximum number of results. |
| `use_wildcard` | `bool` | `True` | `False` for regex search, `True` (default) for wildcard matching. |
| `user_specified_files` | `list[str]` | `[]` | Absolute paths of SPECIFIC individual files the user explicitly names in the query (e.g. `my documentation is at /docs/spec.docx`, `search my file /p/a.sv`; multiple files allowed). Set ONLY when concrete file path(s) are given. When set, the targeted engine searches ONLY these files. Also set `search_engine_name` to match the file's content (documentation `.pdf`/`.docx`/`.txt`/`.md` → `Docs`; source/RTL → `Sources`; `.log`/`.rpt` → `Logs`). |
| `user_specified_filelists` | `list[str]` | `[]` | Absolute paths of FILELIST files the user names — a filelist (commonly `.lst`/`.f`/`.list`) is a text file whose lines ARE the files to search (e.g. `search the files listed in /p/files.lst`). Set ONLY when the user refers to a list/manifest file, NOT the files themselves. When set, the engine reads the list and searches ONLY those files. |
| `user_specified_dirs` | `list[str]` | `[]` | Absolute director(ies) the user explicitly names (e.g. `look under /proj/rtl`). Set ONLY when concrete dir(s) are given. When set, the targeted engine searches ONLY these directories. |

## Steps

1. Use `onesearch_search_db()` to perform a database search.

2. Extract the search keyword from the user query and set:
   - `key_word=<keyword>`

3. Decide the **search engine** (database scope).
   Use the following **trigger table** — match the FIRST row whose trigger
   words appear in the user query. Singular and plural forms both count,
   as do the `"<word> file/files"` variants:

   | Trigger words in the query (any form below)                                 | `search_engine_name`     |
   |-----------------------------------------------------------------------------|--------------------------|
   | `source`, `sources`, `source file`, `source files`, `src file`, `src files` | `"Sources"`              |
   | `log`, `logs`, `log file`, `log files`                                      | `"Logs"`                 |
   | `doc`, `docs`, `document`, `documents`, `documentation`                     | `"Docs"`                 |
   | `identifier`, `identifiers`                                                 | `"Identifiers"`          |
   | (none of the above)                                                         | OMIT — defaults to `All` |

   Notes:
   - The singular form **`source file`** (as in "find En_A in my source file")
     MUST map to `Sources`. Do NOT default to `Logs` just because some
     previous query used logs — only the words in the CURRENT query matter.
   - Do NOT pass `search_engine_name="All"` explicitly; omit it instead.

4. Decide **matching mode**:

   - If the query explicitly mentions:
     - `regex`
     - `regexp`
     - `regular expression`
   - Then:
     ```python
     use_wildcard=False
     ```
   - Explanation:
     - `use_wildcard=False` means **regex mode**
     - This parameter must be set **only when regex is explicitly requested**

   - Otherwise:
     - **Do NOT pass `use_wildcard`**
     - Default behavior uses **wildcard matching**

5. Decide **result limit**:
   - If the query specifies a number of results  
     Examples: `show 10 results`, `limit to 20`, `top 5 results`
     - Action:
       ```python
       max_results=<number>
       ```
   - Otherwise:
     - **Do NOT pass `max_results`**

6. Decide **multi-keyword combination** (when user mentions multiple search terms):

   The syntax depends on the current matching mode:

   **Wildcard mode** (`use_wildcard=True` or default — no `use_wildcard` parameter passed):
   - **OR** ("A or B"): Join with `||` (double pipe, **no spaces**) inside one token:
     ```python
     key_word="clock||reset"
     ```
   - **AND** ("A and B", "both A and B"): Use `+` prefix on each term, separated by space:
     ```python
     key_word="+clock +reset"
     ```
   - **NOT** ("A but not B", "A excluding B"): Use `-` prefix on excluded term:
     ```python
     key_word="clock -test"
     ```
   - **Combined**: `key_word="+clock +reset -test"` (AND + NOT), `key_word="clock||reset -test"` (OR + NOT)

   **Regex mode** (`use_wildcard=False`):
   - **OR** ("A or B"): Use `|` (**single** pipe — native regex alternation):
     ```python
     key_word="clock|reset"
     ```
     Do NOT use `||` in regex mode — `||` means "A OR empty OR B" in regex.
   - **AND** ("A and B"): Same as wildcard: `key_word="+clock +reset"`
   - **NOT** ("A but not B"): Same as wildcard: `key_word="clock -test"`

---

## STRICT Parameter Passing Rules (MANDATORY)

- ✅ Pass **only** parameters explicitly triggered by user intent  
- ❌ Do NOT pass parameters with default or inferred values  
- ❌ Do NOT pass parameters as `False` unless explicitly required by a trigger

---

## Correct Call Examples

### Example 1
**Input**  
> Using onesearch to find clock

```python
onesearch_search_db(key_word="clock")
```

---

### Example 2
**Input**  
> Search docs for dock*

```python
onesearch_search_db(
  key_word="dock*",
  search_engine_name="Docs"
)
```

---

### Example 3
**Input**  
> OneSearch find En_C.* using regex

```python
onesearch_search_db(
  key_word="En_C.*",
  use_wildcard=False
)
```

---

### Example 4
**Input**  
> Search identifiers for SearchEngine

```python
onesearch_search_db(
  key_word="SearchEngine",
  search_engine_name="Identifiers"
)
```

---

### Example 5
**Input**  
> Search docs for dock*, show 10 results

```python
onesearch_search_db(
  key_word="dock*",
  search_engine_name="Docs",
  max_results=10
)
```

---

## Common Errors to Avoid

### Error 1: Passing default values explicitly
❌
```python
onesearch_search_db(
  key_word="clock",
  use_wildcard=True
)
```

✅
```python
onesearch_search_db(key_word="clock")
```

---

### Error 2: Using regex without explicit trigger
❌
```python
onesearch_search_db(
  key_word="En_C.*",
  use_wildcard=False
)
```
(when the user did NOT mention regex)

✅  
Only set `use_wildcard=False` when regex is explicitly requested.

---

### Error 3: Passing unused parameters
❌ Passing `search_engine_name="All"`  
✅ Omit the parameter entirely

### Error 4: Conflicting instructions in the user query
- If multiple instructions conflict (e.g., user mentions both “regex” and “wildcard”), apply **the last, clearest instruction** in the user’s request.
- If ambiguity remains, **ask for clarification** before calling the function.

### Error 5: Passing empty values
❌ `max_results=None`  
✅ Omit the parameter entirely when not explicitly provided with a valid value

### Error 6: Using wrong OR syntax for the matching mode
❌ In wildcard mode (default):
```python
onesearch_search_db(key_word="clock|reset")
```
Single `|` is escaped to literal in wildcard mode.

✅ In wildcard mode, use `||`:
```python
onesearch_search_db(key_word="clock||reset")
```

❌ In regex mode:
```python
onesearch_search_db(key_word="clock||reset", use_wildcard=False)
```
`||` means "clock OR empty OR reset" in regex.

✅ In regex mode, use single `|`:
```python
onesearch_search_db(key_word="clock|reset", use_wildcard=False)
```

> **Note:** Different skills may use different parameter names for similar concepts. Do **not** copy parameters across skills by analogy (e.g., `use_regex` in GUI vs. `use_wildcard=False` in DB).

---

## Multi-Keyword Examples

### Example 6 — OR in wildcard mode (default)
**Input**
> Using onesearch to find clock or reset

```python
onesearch_search_db(key_word="clock||reset")
```

---

### Example 7 — OR in regex mode
**Input**
> Search clock or reset using regex

```python
onesearch_search_db(
  key_word="clock|reset",
  use_wildcard=False
)
```

---

### Example 8 — AND (both terms must match)
**Input**
> Using onesearch to find clock and reset

```python
onesearch_search_db(key_word="+clock +reset")
```

---

### Example 9 — NOT (exclude a term)
**Input**
> Search clock but not test

```python
onesearch_search_db(key_word="clock -test")
```

---

### Example 10 — Combined AND + NOT
**Input**
> Search clock and reset but not test in sources

```python
onesearch_search_db(
  key_word="+clock +reset -test",
  search_engine_name="Sources"
)
```

---

### Example 11 — OR + NOT in wildcard mode
**Input**
> Search clock or reset excluding test

```python
onesearch_search_db(key_word="clock||reset -test")
```

---

## Domain Trigger Examples (singular / informal phrasing)

These examples cover the exact phrasing patterns from real user prompts. Note how singular `"source file"` /
`"log file"` etc. behave identically to the plural forms.

### Example 12 — singular "source file"
**Input**
> find En_A in my source file

```python
onesearch_search_db(
  key_word="En_A",
  search_engine_name="Sources"
)
```

### Example 13 — singular "log file"
**Input**
> find timeout in my log file

```python
onesearch_search_db(
  key_word="timeout",
  search_engine_name="Logs"
)
```

### Example 14 — singular "document"
**Input**
> search clock_gate in the user guide document

```python
onesearch_search_db(
  key_word="clock_gate",
  search_engine_name="Docs"
)
```

### Example 15 — "identifier" / "Identifiers"
**Input**
> find symbol En_A

```python
onesearch_search_db(
  key_word="En_A",
  search_engine_name="Identifiers"
)
```

---

## User-Specified Files / Filelists / Directories

When the user names a **concrete path** in the query, route it by KIND and set
`search_engine_name` to the engine matching that path's content. The engine then
searches ONLY those inputs. Do NOT populate these for generic queries that name no path.

- Individual file(s) → `user_specified_files` (multiple files are bundled automatically).
- A **filelist** file whose lines are the files to search (`.lst`/`.f`/`.list`) → `user_specified_filelists`.
- A directory → `user_specified_dirs`.

If a named path does not exist, the tool reports it back instead of silently ignoring it.

### Example 16 — user names a documentation file (.docx)
**Input**
> my documentation is at /home/me/spec.docx, find En_A

```python
onesearch_search_db(
  key_word="En_A",
  search_engine_name="Docs",
  user_specified_files=["/home/me/spec.docx"]
)
```

### Example 17 — user names a source file
**Input**
> search my source file /proj/rtl/alu.sv for clk

```python
onesearch_search_db(
  key_word="clk",
  search_engine_name="Sources",
  user_specified_files=["/proj/rtl/alu.sv"]
)
```

### Example 18 — user names a directory
**Input**
> look under /proj/rtl for reset

```python
onesearch_search_db(
  key_word="reset",
  search_engine_name="Sources",
  user_specified_dirs=["/proj/rtl"]
)
```

### Example 19 — user names a filelist (.lst/.f/.list)
**Input**
> search the files listed in /home/me/docs.lst for En_A

```python
onesearch_search_db(
  key_word="En_A",
  search_engine_name="Docs",
  user_specified_filelists=["/home/me/docs.lst"]
)
```
