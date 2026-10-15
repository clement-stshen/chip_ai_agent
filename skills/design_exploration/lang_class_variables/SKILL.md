---
name: lang_class_variables
target: [design_exploration]
description: |
  NPI types and APIs for searching variables only (not nets).
match_conditions:
  target_object_class: ["variable"]
---

## Variable Class

### For hier_tree_trv, register these NPI types:
- npiReg
- npiPackedArrayVar
- npiBitVar
- npiStructVar
- npiUnionVar
- npiArrayVar
- npiShortRealVar
- npiRealVar
- npiByteVar
- npiShortIntVar
- npiIntVar
- npiLongIntVar
- npiIntegerVar
- npiTimeVar
- npiEnumVar
- npiStringVar
- npiClassVar
- npiVirtualInterfaceVar
- npiChandleVar

### For single-level access:
```python
variables = scope_hdl.variables_handles()
```

## Parameter Access (CRITICAL)

### Get parameters in a scope:
```python
params = scope_hdl.parameter_handles()
```

### Get parameter value (MANDATORY pattern):
```python
# CORRECT - must use const_type() as format_type argument
for param in scope_hdl.parameter_handles():
    const_t = param.const_type()
    val = param.value(False, const_t)
    # val is the parameter's actual value (e.g., 16, 100)
```

### WRONG patterns (NEVER do these):
```python
# WRONG 1 - using arbitrary format string
val = param.value(False, 'd')  # ERROR!

# WRONG 2 - calling value() without const_type()
val = param.value()  # ERROR!

# WRONG 3 - using None as format_type
val = param.value(False, None)  # ERROR!
```

The `value()` API signature is: `value(is_get_default=False, format_type=None)`
- `format_type` MUST be the return value of `const_type()` on the same handle
- Without correct `format_type`, the return value is undefined
