---
name: evaluate_assertion
description: |
  Trigger evaluation of a specific assertion and return the resulting status and
  timestamps. Use in two cases:
  (1) The assertion has no evaluation data at all (never been run — no timestamps,
      no status recorded). Evaluate automatically without asking the user.
  (2) The user explicitly asks to evaluate a specific assertion, even if its status
      is not_checked or no_attempt.
  Do NOT use this skill just because an assertion is no_attempt —
  that is a terminal state where re-evaluation will not change the result unless
  the user explicitly requests it.
target: [assertion]
examples:
  - "Evaluate assertion <assertion_name>."
  - "Run evaluation for assertion <assertion_name>."
  - "The assertion <assertion_name> has no data, please evaluate it."
  - "Trigger evaluation of <assertion_name>."
  - "Force evaluate assertion <assertion_name> even though it is not checked."
  - "Re-evaluate <assertion_name>."
---

## Overview

Trigger evaluation of a specific assertion and return the resulting status and
timestamps. Only use this skill when the assertion has truly no evaluation data,
or when the user explicitly requests evaluation.

## When to Use

| Situation | Action |
|---|---|
| Assertion has no data at all (never evaluated) | Evaluate immediately, no confirmation needed |
| User explicitly asks to evaluate | Evaluate regardless of current status |
| Assertion is `not_checked` (data not yet available) | Evaluate immediately — data is needed |
| Assertion is `no_attempt` (clock never fired or disabled) | Do NOT evaluate unless user explicitly asks |

## Steps

### Step 1: Trigger Assertion Evaluation

- 1.a. Use the assertion name provided (or known from prior context) to trigger evaluation.
- 1.b. Target only the specific assertion by name — do NOT evaluate all assertions.
- 1.c. If the assertion has no data, evaluate it immediately without asking the user.

### Step 2: Read Evaluation Result

- 2.a. The evaluation tool directly returns the result — timestamps and status are included in
  the output. **Do NOT make a separate query** to re-fetch the assertion status.
- 2.b. If the result contains timestamp data, proceed to Step 3.
- 2.c. If the result is still `not_checked` or contains an error message:
  - Report the error message as-is to the user.
  - **STOP immediately. Do NOT retry evaluation.** One evaluation attempt is the maximum.
  - Example message: **"Evaluation attempted but assertion `<assertion_name>` is still not checked: `<error_message>`. No further evaluation will be performed."**

### Step 3: Report Evaluation Results

- 3.a. Display the assertion name and the resulting status.
- 3.b. List each evaluation event with start time, end time, and status in chronological order.
  For Cover assertions, translate raw status before display: `match` = success, `no-match` = failure.

  | # | Status | Start Time | End Time |
  |---|--------|------------|----------|
  | 1 | [status] | [time + unit] | [time + unit] |

## Notes

- Always include time units (ps, ns, us, ms, s) when displaying timestamps.
- Do not save results to file unless the user explicitly requests it.
- For Cover assertions: `match` = success, `no-match` = failure. Never report 0 success when match data exists, and never report 0 failures when no-match data exists.
