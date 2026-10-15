---
name: add_and_save_assertion
description: |
  Add a new SystemVerilog assertion dynamically (from inline code or a file), which
  automatically evaluates it and returns timestamps. Optionally save the assertion to
  a file for future use. Use when the user wants to add, test, or persist a new SVA assertion.
target: [assertion]
examples:
  - "Add assertion: assert property (@(posedge clk) req |-> ##1 ack);"
  - "Add assertion from file <file_path>."
  - "Add and save assertion <sva_code>."
  - "Create a new assertion to check <condition>."
  - "Add a temporary assertion for <signal> and save it."
---

## Overview

Add a SystemVerilog assertion dynamically. The add operation automatically commits
the SVA and runs evaluation in one step. Optionally save the result to a file.

## Steps

### Step 1: Add the Assertion

- 1.a. Add the assertion using the inline SVA code or file path provided by the user.
- 1.b. The add operation automatically evaluates the assertion after committing — do **not**
  call evaluate separately for the same assertion unless the user explicitly requests a new run.
- 1.c. Record the timestamps returned from the add operation.

### Step 2: Report Evaluation Results

- 2.a. Display the added assertion name/code and its evaluation result.
- 2.b. Report timestamps in chronological order with status (Pass/Fail/Incomplete),
  start time, and end time (with time units).

  | # | Status | Start Time | End Time |
  |---|--------|------------|----------|
  | 1 | [status] | [time + unit] | [time + unit] |

### Step 3: Save the Assertion (if requested)

- 3.a. If the user asks to save the assertion, save it to the specified file path.
- 3.b. Confirm the file path where the assertion was saved.
- 3.c. If the user did not ask to save, skip this step — do not save automatically.

## Notes

- The add operation already includes evaluation — never re-evaluate in the same workflow
  unless the user explicitly asks for a new evaluation run.
- Always include time units when displaying timestamps.
