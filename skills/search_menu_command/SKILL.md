---
name: search_menu_command
description: |
  Search menu items, actions, and keyboard shortcuts by keyword.
  IMPORTANT: Before using this skill, first read onesearch_common for mandatory parameter generation rules.
target: [onesearch]
examples:
  - "Find menu for trace"
  - "Find action for trace, save to mymenu.txt"
---

## Input Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `key_word` | `str` | *(required)* | The keyword to search for in menu commands. |
| `report_file` | `str \| None` | `None` | Output file path for the search report. MUST be set when user says: 'save to X', 'save result into X', 'save result in X', 'save into X', 'save to file X', 'report file X', 'output to X'. Example: `'mygui.txt'` or `'/path/to/results.rpt'`. |

## Steps

1. Use `onesearch_search_menu_command(key_word=<keyword>)` to search menu commands and shortcuts.

2. Extract the **ACTUAL search keyword** from the user query.
   - The keyword is the **subject being searched for**, NOT the type or category.
   - Words such as `menu`, `action`, `shortcut`, `command` describe **where to search**, not **what to search**.

3. Keyword extraction rules and examples:

   - **Example A**
     - Query: `Find menu for trace`
     - `key_word="trace"`
     - Explanation: `menu` is a type descriptor; `trace` is the search target.

   - **Example B**
     - Query: `Find action for open fsdb`
     - `key_word="open fsdb"`
     - Explanation: `action` describes the menu item type; `open fsdb` is the actual keyword.

   - **Example C**
     - Query: `Search menu commands for zoom`
     - `key_word="zoom"`

   - **General Pattern**
     - `Find {type} for {keyword}`
     - `Find {type} containing {keyword}`
     - `Search {type} for {keyword}`
     - Where type ∈ {menu, action, command, shortcut}
     - → `key_word = {keyword}`

4. **Default behavior**
   - By default, call the function with **ONLY** `key_word`.
   - Do **NOT** add any other parameters unless explicitly requested by the user.

5. **Optional parameter: report_file**
   - Add `report_file=<X>` **ONLY IF** the user explicitly requests output.
   - Trigger phrases include:
     - `save to <X>`
     - `save result to <X>`
     - `report file to <X>`
     - `output to <X>`

---

## STRICT Parameter Rules (MANDATORY)

- ✅ If no output-related trigger is present:
```python
onesearch_search_menu_command(key_word="trace")
```

- ✅ If an output file is explicitly requested:
```python
onesearch_search_menu_command(
  key_word="trace",
  report_file="mymenu.txt"
)
```

- ❌ Incorrect:
```python
onesearch_search_menu_command(
  key_word="trace",
  report_file=""
)
```

- ❌ Incorrect:
```python
onesearch_search_menu_command(
  key_word="menu"
)
```

---

## Common Errors to Avoid

1. **Using the type descriptor as the keyword**  
   ❌ `key_word="menu"`  
   ✅ `key_word="trace"`

2. **Automatically adding `report_file`**  
   ❌ Adding `report_file` when the user did not ask to save or output  
   ✅ Only add it when explicitly triggered

3. **Splitting meaningful phrases**  
   ❌ `key_word="open"`  
   ✅ `key_word="open fsdb"`

4. **Conflicting instructions in the user query**  
   - If instructions conflict, apply **the last, clearest instruction**; otherwise **ask for clarification**.

5. **Passing empty values**  
   ❌ `report_file=""`  
   ✅ Omit the parameter entirely when not explicitly provided with a valid value

> **Note:** Different skills may use different parameter names for similar concepts. Do **not** copy parameters across skills by analogy (e.g., `use_regex` in GUI vs. `use_wildcard=False` in DB).

---

## Multi-Keyword Search

Menu command search does **NOT** support multi-keyword syntax in a single call. The entire `key_word` is matched as a literal substring.

If the user asks for multiple keywords (e.g., "find menu for trace or debug"), plan **multiple separate** `onesearch_search_menu_command` calls — one per keyword.

### Example — OR across menu commands (multi-step plan)
**Input**
> Find menu for trace or debug

**Plan**
```
1. Use `onesearch_search_menu_command(key_word='trace')` to search menu commands for 'trace'.
2. Use `onesearch_search_menu_command(key_word='debug')` to search menu commands for 'debug'.
```

### Example — AND across menu commands (multi-step plan)
**Input**
> Find menu commands related to both zoom and wave

**Plan**
```
1. Use `onesearch_search_menu_command(key_word='zoom')` to search menu commands for 'zoom'.
2. Use `onesearch_search_menu_command(key_word='wave')` to search menu commands for 'wave'.
```

---

## Summary

- The keyword is **what to search for**, not **where to search**.
- Default call = `key_word` only.
- `report_file` must be **explicitly triggered**.
- Never infer or auto-fill optional parameters.
- For multi-keyword queries, plan **multiple separate calls** — one per keyword.
