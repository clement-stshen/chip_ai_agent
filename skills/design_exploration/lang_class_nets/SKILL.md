---
name: lang_class_nets
target: [design_exploration]
description: |
  NPI types and APIs for searching nets only (not variables).
match_conditions:
  target_object_class: ["net"]
---

## Net Class

### For hier_tree_trv, register these NPI types:
- npiNet
- npiArrayNet
- npiPackedArrayNet
- npiStructNet
- npiEnumNet
- npiIntegerNet
- npiTimeNet

### For single-level access:
```python
nets = list(scope_hdl.net_handles()) + list(scope_hdl.array_net_handles())
```
