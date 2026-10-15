---
name: lang_class_scopes
target: [design_exploration]
description: |
  NPI types and APIs for searching all scope types (includes instances and other scopes).
match_conditions:
  target_object_class: ["scope"]
---

## Scope Class (Instances + Other Scope Types)

### For hier_tree_trv, register these NPI types:

**Instance types:**
- npiModule
- npiInterface
- npiPackage
- npiProgram

**Other scope types:**
- npiNamedBegin
- npiBegin
- npiNamedFork
- npiFork
- npiGenScope
- npiFor
- npiClassObj
- npiClassDefn
- npiClassTypespec
- npiForeachStmt
- npiTask
- npiFunction

### For single-level access:
```python
scopes = scope_hdl.internal_scope_handles()
```

### To get parent scope:
```python
parent = hdl.scope_handle()
```
