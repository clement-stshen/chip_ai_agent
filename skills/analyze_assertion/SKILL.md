---
name: analyze_assertion
description: |
  Analyze a specific assertion by name to determine its status, evaluate it if no data exists,
  and report the problem signals with timestamps, expected behavior, and the failing expression.
  Use when the user wants to analyze or debug a named assertion.
target: [assertion]
examples:
  - "Analyze assertion <assertion_name>."
  - "Debug assertion <assertion_name>."
  - "What is wrong with assertion <assertion_name>?"
  - "Analyze the failure of assertion <assertion_name>."
  - "Check why assertion <assertion_name> is failing."
  - "Investigate assertion <assertion_name>."
  - "analyze assertion <name> fail"
  - "analyze assertion <name> failure"
---

## Overview

**IMPORTANT**: Call `analyze_assertion_status()` directly as your FIRST and ONLY tool call.
Do NOT call `get_assertion_statistics()` — it is the WRONG tool for analyzing assertions.

**If the result contains `failure_reason` or `do_not_retry: true`, stop immediately.
Do NOT call `analyze_assertion_status()` again with the same `assertion_name`.
Report the failure reason to the user and stop.**

## Steps

### Step 1: Analyze the Assertion

- 1.a. **Call `analyze_assertion_status()` directly** with:
  - `assertion_name`: The full hierarchical assertion name (e.g., "test.data_check")
  - `status_type`: `'failure'` (default if the user does not specify)
- 1.b. **CRITICAL: Do NOT call `get_assertion_statistics()` or `evaluate_assertion()` first.**
  These are WRONG tools for this task. `analyze_assertion_status()` handles everything internally.
- 1.c. **If `analyze_assertion_status()` fails or returns no data, do NOT retry
  with the same `assertion_name`.** Report the result as-is and explain to the user
  what was found (e.g., no failure data exists, assertion was not attempted, or
  evaluation could not be triggered). Calling the tool again with the same name
  will not produce different results.

### Step 2: Report Results

- 2.a. From the result, extract and report:
  - **Problem signals**: The signals involved in the failing expression
  - **Timestamp**: When the failure occurred (with time unit)
  - **Expected behavior**: What the assertion required at that time
  - **Failing expression**: The specific sub-expression that evaluated to FALSE
- 2.b. Present the result in a structured format:

  | Signal | Timestamp | Expected Behavior | Failing Expression |
  |--------|-----------|-------------------|--------------------|
  | [signal_name] | [time + unit] | [expected value/condition] | [expression] |

- 2.c. **When a clock edge and a signal value change occur at the same simulation time, treat the assertion engine's sampled result as the source of truth.**

## Notes

- **MUST call `analyze_assertion_status()` directly — never call `get_assertion_statistics()` or `evaluate_assertion()` first when the user asks to analyze.**
- **Never call `analyze_assertion_status()` again with the same `assertion_name` after a failure or empty result** — the outcome will be identical. Report what was found and stop.
- Always include time units when reporting timestamps.
- If the user does not specify a status type, analyze failure first.
