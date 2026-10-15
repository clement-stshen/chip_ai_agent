---
name: lang_struct_member
target: [design_exploration]
description: |
  Handle struct/union member signal queries.
match_conditions:
  has_struct_member_query: true
---

## When to Use
User asks to include struct/union member signals, record fields, or packed struct access.

## Key APIs
- `hdl.member_handles()` - Get member signals inside struct/union

## Struct/Union NPI Types
- `npiStructNet` - Struct net
- `npiStructVar` - Struct variable
- `npiUnionVar` - Union variable

## Steps

### Step 1: Identify struct/union types
Check if handle type is one of:
- npiStructNet
- npiStructVar
- npiUnionVar

### Step 2: Get members and construct full names
```python
def get_struct_members(hdl, results):
    """Recursively collect struct/union members."""
    if hdl.type() not in ["npiStructNet", "npiStructVar", "npiUnionVar"]:
        return

    members = hdl.member_handles()
    for member in members:
        # Member's full name = parent's full_name + "." + member's name()
        member_full_name = hdl.full_name() + "." + member.name()
        results.append({
            "identifier": member_full_name,
            "attributes": {"type": member.type()}
        })

        # Recursively process nested structs
        if member.type() in ["npiStructNet", "npiStructVar", "npiUnionVar"]:
            get_struct_members(member, results)

        lang.release_handle(member)
```

### Step 3: Use with signal collection
When collecting signals and user asks to include struct members:
```python
for hdl in scope.net_handles():
    results.append({"identifier": hdl.full_name(), "type": hdl.type()})
    # If user wants struct members, expand them
    if hdl.type() in ["npiStructNet", "npiStructVar", "npiUnionVar"]:
        get_struct_members(hdl, results)
```

## Full Name Construction Rule

**CRITICAL**: Member's full name is constructed by concatenating:
- Parent's `full_name()` + `"."` + Member's `name()`

**Example:**
If `hdl.full_name()` is `"top.cpu.data_bus"` (a struct),
and member's `name()` is `"addr"`,
then member's full name is `"top.cpu.data_bus.addr"`

## IMPORTANT
- Struct members are accessed via `member_handles()`, not via traversal
- Member's full name is constructed by concatenating parent's full_name with member's name
- Members themselves can be nested structs - handle recursively
- Always release member handles after processing
