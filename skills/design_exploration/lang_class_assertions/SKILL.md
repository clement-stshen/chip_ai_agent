---
name: lang_class_assertions
target: [design_exploration]
description: |
  NPI types and APIs for searching assertions (SVA assertions, assumes, covers).
match_conditions:
  target_object_class: ["assertion"]
---

## Assertion Class

### For hier_tree_trv, register these NPI types:
- npiAssert
- npiImmediateAssert
- npiAssume
- npiImmediateAssume
- npiCover
- npiImmediateCover

### For single-level access:
Use different methods depending on scope type:

**For instance types (npiModule, npiInterface, npiPackage, npiProgram):**
```python
assertions = scope_hdl.assertion_handles()
```

**For other scope types:**
```python
assertions = scope_hdl.concurrent_assertion_handles()
```
