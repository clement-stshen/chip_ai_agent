---
name: lang_class_signals
target: [design_exploration]
description: |
  NPI types and APIs for searching signals (nets + variables).
match_conditions:
  target_object_class: ["signal"]
---

## Signal Class = Net + Variable

### For hier_tree_trv, register these NPI types:

**Net types:**
- npiNet
- npiArrayNet
- npiPackedArrayNet
- npiStructNet
- npiEnumNet
- npiIntegerNet
- npiTimeNet

**Variable types:**
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

### For single-level access, use these *_handles() methods:
```python
signals = list(scope_hdl.net_handles()) + list(scope_hdl.array_net_handles()) + list(scope_hdl.variables_handles())
```

## IMPORTANT
- "input/output signals" actually means "input/output ports" - see port_direction skill
- Signals do NOT have direction; only ports have direction
