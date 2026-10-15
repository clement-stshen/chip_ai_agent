---
name: lang_logic_type
target: [design_exploration]
description: |
  Find signals of 'logic' type by unwrapping array typespecs.
match_conditions:
  has_logic_type_query: true
---

## When to Use
User asks for signals of type 'logic' (SystemVerilog logic type).

## NPI Types to Register
For logic type signals, register these types:
- npiReg
- npiNet
- npiArrayVar
- npiArrayNet

## Key APIs
- `hdl.typespec_handle()` - Get the typespec handle
- `typespec.elem_typespec_handle()` - Unwrap one array dimension
- `typespec.type()` - Check if it's npiLogicTypespec

## Logic Type Detection Pattern

For `npiArrayVar` and `npiArrayNet`, you need to unwrap array dimensions
to check the base element type. Each call to `elem_typespec_handle()`
removes one array dimension until you reach the base type.

```python
def is_logic_type(hdl):
    """Check if signal is of logic type."""
    hdl_type = hdl.type()

    # Direct logic types
    if hdl_type in ["npiReg", "npiNet"]:
        return True

    # Array types need unwrapping
    if hdl_type in ["npiArrayVar", "npiArrayNet"]:
        typespec = hdl.typespec_handle()
        if typespec is None:
            return False

        # Unwrap array dimensions using while loop
        # Each iteration removes one array dimension
        while typespec is not None and typespec.type() == "npiArrayTypespec":
            inner_typespec = typespec.elem_typespec_handle()
            lang.release_handle(typespec)
            typespec = inner_typespec

        # Check if base type is logic
        if typespec is not None:
            result = typespec.type() == "npiLogicTypespec"
            lang.release_handle(typespec)
            return result

    return False
```

## Steps

### Step 1: Register callbacks for relevant types
```python
results = []

def collect_logic_cb(hdl, cb_data):
    if is_logic_type(hdl):
        cb_data.append(hdl.full_name())

lang.hier_tree_trv_register_cb("npiReg", collect_logic_cb, results)
lang.hier_tree_trv_register_cb("npiNet", collect_logic_cb, results)
lang.hier_tree_trv_register_cb("npiArrayVar", collect_logic_cb, results)
lang.hier_tree_trv_register_cb("npiArrayNet", collect_logic_cb, results)
```

### Step 2: Traverse and collect
```python
for top in lang.get_top_inst_list():
    if top.type() == "npiModule":
        lang.hier_tree_trv(top.full_name())
lang.hier_tree_trv_reset_cb()
```

## IMPORTANT
- The `elem_typespec_handle()` method removes one array dimension per call
- Use a while loop to unwrap all array dimensions until you reach the base type
- Check for `npiLogicTypespec` at the base level
- Always release typespec handles after use
- This pattern is shown in PyNPIDoc Example #23
