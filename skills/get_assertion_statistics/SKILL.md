---
name: get_assertion_statistics
description: |
  Get assertion statistics for the design, with optional filtering by scope, FSDB file,
  assertion name, status type, or assertion type (Assert/Assume/Cover). Returns counts of
  failure/success/incomplete/no attempt/not checked assertions and a preview of assertion names.
  Also shows the assertion statistics on the GUI.
  Use when the user wants an overview of assertion results, wants to filter by scope, FSDB,
  assertion type, or wants to list all assertions with a specific status, or wants to show
  the assertion statistics GUI.
target: [assertion]
examples:
  - "Get assertion statistics."
  - "How many assertions failed?"
  - "Show me all failure assertions."
  - "Get assertion statistics for scope <scope>."
  - "Get assertion statistics filtered by the loaded FSDB file."
  - "List all incomplete assertions."
  - "How many assertions passed in <fsdb_file>?"
  - "Show assertion statistics for <scope> in <fsdb_file>."
  - "Get all assertion status summary."
  - "Show all cover assertions that failed."
  - "List failed cover type assertions."
  - "How many assume assertions are incomplete?"
  - "Show only Assert type assertions."
  - "Show all assert property status in the design."
  - "What is the status of all assertions?"
  - "Give me a summary of all assertion results."
  - "Show me the not checked assertions."
  - "Which assertions are not checked?"
  - "Show timestamps for <assertion_name>."
  - "Get failure timestamps for <assertion_name>."
---

## Overview

Retrieve assertion statistics with optional filters. Avoid fetching all data when
a specific assertion name is already known — use targeted queries in that case.

**Call `get_assertion_statistics` as few times as possible.** The summary call already
returns per-status assertion name lists. Do not make a second call to retrieve names
for a status that was already included in a previous result.

## Steps

### Step 1: Determine Filter Parameters

- 1.a. Identify what filters the user provides:
  - **Assertion name**: If provided, use it as a filter — do not fetch all assertions.
  - **Scope**: If provided, filter statistics to that hierarchical scope.
  - **FSDB file**: If provided, filter statistics to that FSDB file. Assume the FSDB file is already loaded.
  - **Status type**: If provided (failure/success/incomplete/no attempt/not checked), filter by that status.
  - **Assertion type**: If the user mentions a type — `Assert`, `Assume`, or `Cover` — pass it as `assertion_type`.
    - Use `assertion_type='Cover'` when user asks about cover assertions.
    - Use `assertion_type='Assume'` when user asks about assume assertions.
    - Use `assertion_type='Assert'` when user asks about assert (property) assertions.
- 1.b. If no filters are provided, fetch the full assertion statistics summary.

### Step 2: Get Assertion Statistics

- 2.a. Call `get_assertion_statistics()` with the determined filter parameters.
- 2.b. If filtering by assertion name, always pass the name — never omit it when known.
- 2.c. If filtering by assertion type, pass `assertion_type` (e.g., `assertion_type='Cover'`).
- 2.d. Combine filters freely — for example, `assertion_type='Cover'` with `status_type='failure'` to show only failed cover assertions.
- 2.e. **Do not make a follow-up call with `status_type` to retrieve assertion names that are already present in the current result's preview.** Reuse the names from the existing result instead.
- 2.f. **Do not fetch per-assertion timestamps** unless the user explicitly asks for timestamps or failure details. A status overview does not require individual assertion queries.

### Step 3: Report Statistics

- 3.a. Always report **both** the summary counts **and** the assertion names preview — never omit either.
- 3.b. Present the summary in this format:

  | Status | Count |
  |--------|-------|
  | Failure | [n] |
  | Success | [n] |
  | Incomplete | [n] |
  | No Attempt | [n] |
  | Not Checked | [n] |

- 3.c. List all assertion names shown in the preview beneath the table.
- 3.d. Mention the file path where the full list is saved, but **the preview content is more important** — always display it inline.
- 3.e. **Important — counts are assertion name membership counts, not event counts.**
  `failures_assertions: 1` means 1 assertion name has at least one failure event — it does NOT
  mean the assertion failed exactly 1 time. The same assertion name can appear in both
  `successes_assertions` and `failures_assertions` if it has both success and failure events.
  To get the actual number of failure/success events for a specific assertion, query it by
  name with `get_assertion_timestamps=True`.

### Step 4: Handle No Data / Not Checked / No Attempt Assertions

- 4.a. If the result returns **no data at all** (no assertions matched, no timestamps, no status
  recorded) **or** the status is **`not_checked`** (evaluation data is unavailable):
  **Immediately trigger evaluation without asking the user**, then re-run Step 2 to get updated statistics.
  - `not_checked` means the assertion has not been evaluated yet and data is not available —
    evaluation is needed to obtain results.
- 4.b. If the statistics show assertions with **No Attempt** status, report them as-is.
  **Do NOT trigger evaluation** — `no_attempt` means the assertion was present but the clock
  never fired or it was disabled via `$assertoff()`. Re-evaluation will not change the result.
- 4.c. Note the no-attempt assertion names in the report and stop.

## Notes

- When an assertion name is already known, use targeted assertion tools instead of statistics.
- Do not save statistics to file unless the user explicitly requests it.
- Always include the assertion names preview in the response — never summarize or omit it.
- **Minimize tool calls**: one summary call is usually sufficient. Only make additional calls when the user explicitly requests more detail or a different filter that cannot be satisfied from the existing result.
