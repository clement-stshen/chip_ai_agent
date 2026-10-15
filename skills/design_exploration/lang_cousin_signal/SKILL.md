---
name: lang_cousin_signal
target: [design_exploration]
description: |
  Handle "cousin signal" queries - signals from sibling modules sharing the same parent.
match_conditions:
  has_cousin_query: true
---

## When to Use
User asks for "cousin signals" of a signal.

## Definition
"Cousin signals" are signals from sibling modules that share the same parent module.

Example: If `a.b.c` is a signal:
- Its module is `a.b`
- Its parent module is `a`
- Its cousin signals are signals under all child modules of `a` EXCEPT `a.b`

## Steps

### Step 1: Parse the signal path
Given signal `a.b.c.sig`:
- Parent scope of signal: `a.b.c`
- Grandparent scope: `a.b`

### Step 2: Get grandparent scope
```python
# Remove last two segments to get grandparent
signal_path = "a.b.c.sig"
parts = signal_path.rsplit(".", 2)
grandparent = parts[0] if len(parts) > 2 else None
parent_scope = ".".join(parts[:-1])  # a.b.c
```

### Step 3: Traverse from grandparent, exclude original parent
Use hier_tree_trv starting from grandparent, but skip the original parent scope.

```python
def skip_cb(hdl, cb_data):
    # Skip the original parent scope
    if hdl.full_name() == parent_scope:
        return True
    return False
```

### Step 4: Collect cousin signals
Register signal types and traverse from grandparent.
