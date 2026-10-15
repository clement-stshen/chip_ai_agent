---
name: search_gui_content
description: |
  Search which GUI windows, panels, or tree views contain the specified keyword.
target: [onesearch]
examples:
  - "Find which windows contain clock"
  - "Search for windows with signal"
---

## Input Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `key_word` | `str` | *(required)* | The keyword to search for in GUI windows/panels. |
| `match_case` | `bool \| None` | `None` | ONLY set when user explicitly says 'case sensitive' or 'ignore case'. Leave `None` otherwise. |
| `use_wildcard` | `bool \| None` | `None` | MUTUALLY EXCLUSIVE with `use_regex` and `find_whole_words_only`. ONLY set `True` when user explicitly says 'wildcard'. Do NOT infer from keyword content. When `True`, OMIT `use_regex` and `find_whole_words_only` entirely. |
| `use_regex` | `bool \| None` | `None` | MUTUALLY EXCLUSIVE with `use_wildcard` and `find_whole_words_only`. ONLY set `True` when user says 'regex' or 'regular expression'. When `True`, OMIT `use_wildcard` and `find_whole_words_only` entirely. |
| `find_whole_words_only` | `bool \| None` | `None` | MUTUALLY EXCLUSIVE with `use_wildcard` and `use_regex`. ONLY set `True` when user says 'exactly match', 'exact match', 'whole word', or 'exact word'. When `True`, OMIT `use_wildcard` and `use_regex` entirely. |
| `report_file` | `str \| None` | `None` | Output file path for the search report. MUST be set when user says: 'save to X', 'save result into X', 'save result in X', 'save into X', 'save to file X', 'report file X', 'output to X'. Example: `'mygui.txt'` or `'/path/to/results.rpt'`. |

## Steps

1. Use `onesearch_search_gui_content(key_word=<keyword>)` to search GUI windows, panels, or trees.

2. Extract the search keyword from the user query and set `key_word=<keyword>`.

3. **By default, pass ONLY `key_word`. Do NOT pass any other parameters.**

4. Add an optional parameter **only if the user query contains an explicit trigger word**.
   - If a parameter is not triggered, **it must NOT appear in the function call** (do not even pass it as `False`).

5. Matching mode parameters (`use_regex`, `use_wildcard`, `find_whole_words_only`) are **MUTUALLY EXCLUSIVE**.
   - If one matching mode is triggered, pass **only that one** as `True`.
   - **Do NOT** pass the other two parameters (do NOT pass them as `False`).

---

## Trigger Words and Parameter Mapping

### 1. Report Output

- **Parameter**: `report_file=<X>`
- **Trigger words**:
  - `save to`
  - `save result to`
  - `report file to`
  - `report into`
  - `output to`
- **Action**:
  - Extract `<X>` from the user query and pass it as `report_file`.

---

### 2. Case Sensitivity

- **Parameter**: `match_case`

| Trigger Words | Value |
|--------------|-------|
| `case sensitive`, `match case` | `match_case=True` |
| `ignore case`, `case insensitive`, `don't care case`, `no case` | `match_case=False` |

⚠️ **Important**  
- Pass `match_case` **only if one of the trigger words appears**.  
- If no case-related trigger appears, **do not pass `match_case` at all**.

---

### 3. Matching Mode (Mutually Exclusive)

Only ONE of the following may be passed, and only when triggered.

#### a. Regular Expression

- **Parameter**: `use_regex=True`
- **Trigger words**:
  - `regex`
  - `regular expression`
  - `using regular expression`

#### b. Wildcard

- **Parameter**: `use_wildcard=True`
- **Trigger words**:
  - `wildcard`
  - `wild card`
  - `use wildcard`

#### c. Exact / Whole Word Match

- **Parameter**: `find_whole_words_only=True`
- **Trigger words**:
  - `exactly match`
  - `exact match`
  - `whole word`
  - `exact word`

6. Decide **multi-keyword combination** (when user mentions multiple search terms):

   - **OR in default partial-match mode** ("A or B"): Join with ` || ` (double pipe, **with spaces**):
     ```python
     key_word="clock || reset"
     ```
     The GUI splits on `||` and trims each segment. Matching returns true if **any** segment matches.

   - **IMPORTANT**: `||` splitting **only** works in default partial-match mode (when `use_wildcard`, `use_regex`, and `find_whole_words_only` are all NOT set). If any matching mode parameter is set, `||` is treated as literal text.

   - **AND**: Not supported in GUI content search. If user asks for AND, plan **two separate** `onesearch_search_gui_content` calls, one per keyword.

---

## STRICT Parameter Passing Rules (MANDATORY)

- ✅ **OK**: Pass only the parameters explicitly triggered by the user.  
- ❌ **NOT OK**: Passing untriggered parameters with `False`.

### ❌ Incorrect
```python
onesearch_search_gui_content(
  key_word="system",
  find_whole_words_only=True,
  use_regex=False,
  use_wildcard=False
)
```

### ✅ Correct
```python
onesearch_search_gui_content(
  key_word="system",
  find_whole_words_only=True
)
```

---

## Examples (Aligned With Real Prompts)

### Example 1
**Input**  
> OneSearch Find which windows have clock

**Call**
```python
onesearch_search_gui_content(key_word="clock")
```

---

### Example 2
**Input**  
> OneSearch Find which tree has En_* use wildcard

**Call**
```python
onesearch_search_gui_content(
  key_word="En_*",
  use_wildcard=True
)
```

---

### Example 3
**Input**  
> OneSearch Find window has CHILD, don't care case

**Call**
```python
onesearch_search_gui_content(
  key_word="CHILD",
  match_case=False
)
```

---

### Example 4
**Input**  
> OneSearch Find window has CHILD, match case

**Call**
```python
onesearch_search_gui_content(
  key_word="CHILD",
  match_case=True
)
```

---

### Example 5
**Input**  
> OneSearch Find tree exactly match system

**Call**
```python
onesearch_search_gui_content(
  key_word="system",
  find_whole_words_only=True
)
```

---

### Example 6
**Input**  
> OneSearch Find window contain clo.* using regular expression

**Call**
```python
onesearch_search_gui_content(
  key_word="clo.*",
  use_regex=True
)
```

---

### Example 7 (Report Output)
**Input**  
> Find windows with error and save result to gui.rpt

**Call**
```python
onesearch_search_gui_content(
  key_word="error",
  report_file="gui.rpt"
)
```

---

## Common Errors to Avoid

### Error 1: Passing `False` for non-triggered parameters
❌ `use_regex=False`, `use_wildcard=False`, `find_whole_words_only=False`  
✅ Remove them completely

### Error 2: Passing multiple matching modes
❌ `use_regex=True` and `use_wildcard=True`  
✅ Keep only the one explicitly requested

### Error 3: Defaulting `match_case`
❌ Always passing `match_case=False`  
✅ Pass `match_case` **only when explicitly triggered**

### Error 4: Conflicting instructions in the user query
- If multiple instructions conflict (e.g., user mentions both “regex” and “wildcard”), apply **the last, clearest instruction** in the user’s request.
- If ambiguity remains, **ask for clarification** before calling the function.

### Error 5: Passing empty values
❌ `report_file=""`  
✅ Omit the parameter entirely when not explicitly provided with a valid value

### Error 6: Using `||` with a matching mode parameter
❌ `||` is NOT interpreted as OR when a matching mode is set:
```python
onesearch_search_gui_content(
  key_word="clock || reset",
  use_wildcard=True
)
```

✅ `||` OR only works in default partial-match mode (no matching mode parameter):
```python
onesearch_search_gui_content(key_word="clock || reset")
```

> **Note:** Different skills may use different parameter names for similar concepts. Do **not** copy parameters across skills by analogy (e.g., `use_regex` in GUI vs. `use_wildcard=False` in DB).

---

## Multi-Keyword Examples

### Example 8 — OR in default partial-match mode
**Input**
> Find windows with clock or reset

**Call**
```python
onesearch_search_gui_content(key_word="clock || reset")
```

---

### Example 9 — OR with three terms
**Input**
> Find which panels contain clock or reset or enable

**Call**
```python
onesearch_search_gui_content(key_word="clock || reset || enable")
```

---

### Example 10 — AND (not supported, use two separate calls)
**Input**
> Find windows that contain both clock and reset

**Plan**
```
1. Use `onesearch_search_gui_content(key_word='clock')` to search GUI windows for 'clock'.
2. Use `onesearch_search_gui_content(key_word='reset')` to search GUI windows for 'reset'.
```
