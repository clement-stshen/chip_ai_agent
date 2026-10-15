---
name: lang_net_type_filter
target: [design_exploration]
description: |
  Filter nets by net type (wire, tri-state, supply, etc.).
match_conditions:
  has_net_type_filter: true
---

## When to Use
User asks for nets of a specific net type:
- wire
- wire-and (wand)
- wire-or (wor)
- tri-state (tri)
- pull-down
- pull-up
- tri-state reg
- tri-state wire-and (triand)
- tri-state wire-or (trior)
- supply 1
- supply zero
- unresolved wire

## Key APIs
- `hdl.net_type()` - Get net type string

## Steps

### Step 1: Search for Net class objects
Use hier_tree_trv or net_handles() to find nets:
- npiNet
- npiArrayNet

### Step 2: Filter by net_type()
```python
def collect_cb(hdl, cb_data):
    net_type = hdl.net_type()
    if net_type == target_net_type:
        cb_data.append(hdl.full_name())
```

## Net Type Values
Common net_type() return values:
- "npiWire"
- "npiWand"
- "npiWor"
- "npiTri"
- "npiTri0"
- "npiTri1"
- "npiTriAnd"
- "npiTriOr"
- "npiTriReg"
- "npiSupply0"
- "npiSupply1"
- "npiUwire"
