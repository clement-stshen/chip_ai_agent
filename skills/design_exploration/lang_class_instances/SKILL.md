---
name: lang_class_instances
target: [design_exploration]
description: |
  NPI types and APIs for searching module/interface/package/program instances.
match_conditions:
  target_object_class: ["instance"]
---

## Instance Class

### For hier_tree_trv, register these NPI types:
- npiModule
- npiInterface
- npiPackage
- npiProgram

### For single-level access:
```python
internal_scopes = scope_hdl.internal_scope_handles()
# Filter for instance types
instance_types = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]
instances = [s for s in internal_scopes if s.type() in instance_types]
```

## IMPORTANT
- Instances are a subset of internal scopes
- Other internal scopes (named blocks, generate scopes) are NOT instances
