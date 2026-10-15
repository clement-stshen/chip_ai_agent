---
name: evaluate_multiple_assertions
description: |
  Evaluate multiple assertions in batch mode. Supports two modes:
  1. Provide specific assertion names to evaluate
  2. Provide a scope to evaluate all assertions under that scope
  This is more efficient than evaluating assertions one at a time.
target: [assertion]
examples:
  - "Evaluate all assertions under scope top.dut."
  - "Evaluate these assertions: assert1, assert2, assert3."
  - "Batch evaluate all cover assertions under top.checker."
  - "Evaluate multiple assertions without asking for confirmation."
  - "Evaluate all assertions in the dut module."
---

## Overview

Evaluate multiple assertions in a single batch operation. You can either:
1. Provide a list of specific assertion names
2. Provide a scope to automatically find and evaluate all assertions under it

This is significantly more efficient than calling `evaluate_assertion` repeatedly.

## When to Use

| Situation | Action |
|---|---|
| Evaluate all assertions under a scope | Use `scope` parameter |
| Evaluate specific assertions by name | Use `scoped_assertion_names` parameter |
| Evaluate only certain types (assert/cover) | Use `assertion_type` parameter with scope |

## Tool Function

```python
evaluate_multiple_assertions(
    scoped_assertion_names: list[str] = None,  # Specific assertion names
    scope: str = None,                          # Scope to find assertions
    assertion_type: str = "all"                 # "assert", "assume", "cover", or "all"
)
```

## Usage Examples

### Example 1: Evaluate All Assertions Under a Scope

```python
# Evaluate all assertions under top.dut
evaluate_multiple_assertions(scope="top.dut")

# Evaluate only cover assertions under top.checker
evaluate_multiple_assertions(scope="top.checker", assertion_type="cover")

# Evaluate only assert type under top.dut
evaluate_multiple_assertions(scope="top.dut", assertion_type="assert")
```

### Example 2: Evaluate Specific Assertions by Name

```python
# Evaluate specific assertions
evaluate_multiple_assertions(
    scoped_assertion_names=["top.dut.assert1", "top.dut.assert2", "top.checker.cover1"]
)
```

### Example 3: Combined - Scope + Additional Assertions

```python
# Evaluate all assertions under scope + some additional ones
evaluate_multiple_assertions(
    scope="top.dut",
    scoped_assertion_names=["top.other.assert_extra"]
)
```

## Steps

### Step 1: Determine Assertions to Evaluate

- 1.a. If user provides a **scope**:
  - The tool automatically queries all assertions under that scope
  - Optionally filter by `assertion_type` (assert, assume, cover, all)
- 1.b. If user provides **specific assertion names**:
  - Use those names directly
- 1.c. Both can be combined - scope assertions + additional names

### Step 2: Execute Batch Evaluation

- 2.a. The tool builds the Tcl command automatically
- 2.b. Uses `-noAsk` by default to skip confirmation dialog
- 2.c. Executes `evalPropAtBgMode` with all assertions

### Step 3: View Results

- 3.a. The Statistics window opens automatically with results
- 3.b. Use `get_assertion_statistics()` to programmatically fetch updated results

## Underlying Tcl Command

```tcl
evalPropAtBgMode {{scope1.assertion1}{scope2.assertion2}...} [-noAsk]
```

## Response Format

The tool returns a summary message:

```
Batch evaluation started for 5 assertion(s) under scope 'top.dut':
top.dut.assert1, top.dut.assert2, top.dut.assert3, ... (2 more)

The Statistics window has been opened with the evaluation results.
Use `get_assertion_statistics()` to fetch the updated assertion status.
```

## Notes

- **Scope uses dot notation**: e.g., `top.dut.submodule` (not `top/dut/submodule`)
- **assertion_type options**: "all", "assert", "assume", "cover"
- The Statistics window opens automatically after evaluation
- For updated results, call `get_assertion_statistics()` after evaluation completes
- Confirmation dialog is always skipped for automation
