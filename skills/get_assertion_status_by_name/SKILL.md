---
name: get_assertion_status_by_name
description: |
  Query the evaluation status (failure, success, incomplete, no attempt, not checked)
  of a specific assertion by its full name, including timestamps of each evaluation event.
  Use when the user wants to know the status or timestamps of a named assertion.
target: [assertion]
examples:
  - "What is the status of assertion <assertion_name>?"
  - "Get the failure timestamps of assertion <assertion_name>."
  - "Show me when assertion <assertion_name> failed."
  - "List all pass timestamps for assertion <assertion_name>."
  - "Did assertion <assertion_name> fail? When?"
  - "Get timestamps for assertion <assertion_name>."
---

## Overview

Query the evaluation status and timestamps of a specific assertion by name without
fetching all assertion data.

## Steps

### Step 1: Query Assertion Status by Name

- 1.a. Use the assertion name provided by the user to query its status directly.
  **Never** fetch all assertion statuses when the name is known — always pass the name as a filter.
- 1.b. Determine the status type to query:
  - If the user specifies a status (failure/success/incomplete), query that status.
  - If not specified, query **failure** first, then report whatever data is available.
- 1.c. Interpret the result:
  - **No data at all** (assertion was never evaluated — no timestamps, no status recorded):
    immediately trigger evaluation for the assertion, then re-query. Do NOT ask the user.
  - **`not_checked`** (assertion could not be evaluated, e.g., a referenced signal was not
    dumped to FSDB, or the SVA has a semantic error): report the status as-is and stop.
    Do NOT auto-evaluate — re-evaluation will not help.
  - **`no_attempt`** (assertion was present but the clock never fired, or disabled via
    `$assertoff()`): report the status as-is and stop. Do NOT auto-evaluate.
  - Exception: if the user **explicitly asks** to evaluate a `not_checked` or `no_attempt`
    assertion, proceed with evaluation regardless.

### Step 2: Report Status and Timestamps

- 2.a. Display the assertion name and status clearly.
- 2.b. List each evaluation event with:
  - **Status**: Pass / Fail / Incomplete
  - **Start time**: When the evaluation was triggered (include time unit)
  - **End time**: When the evaluation completed (include time unit)
- 2.c. Present in chronological order:

  | # | Status | Start Time | End Time |
  |---|--------|------------|----------|
  | 1 | [status] | [time + unit] | [time + unit] |

## Notes

- Always include time units (ps, ns, us, ms, s) when displaying timestamps.
- Do not save results to file unless the user explicitly requests it.
