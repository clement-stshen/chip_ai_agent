---
name: lang_task_function
target: [design_exploration]
description: |
  Handle task and function related queries.
match_conditions:
  has_task_function_query: true
---

## When to Use
User asks about tasks or functions:
- Task definitions
- Task calls
- Function definitions
- Function calls

## NPI Types

### Task related:
- `npiTask` - Task definitions
- `npiTaskCall` - Task calls
- `npiSysTaskCall` - Built-in system task calls (e.g., $display)
- `npiMethodTaskCall` - Class method task calls

### Function related:
- `npiFunction` - Function definitions
- `npiFuncCall` - Function calls
- `npiSysFuncCall` - Built-in system function calls (e.g., $time)
- `npiMethodFuncCall` - Class method function calls

## Steps

### For task/function definitions:
Register npiTask or npiFunction in hier_tree_trv callbacks.

### For task/function calls:
Register corresponding call types (npiTaskCall, npiFuncCall, etc.).

## IMPORTANT
- Definitions (npiTask, npiFunction) and calls (npiTaskCall, npiFuncCall) are different
- System tasks/functions have separate types (npiSysTaskCall, npiSysFuncCall)
- Class method calls also have separate types
