---
name: lang_wildcard_hierarchy
target: [design_exploration]
description: |
  Resolve hierarchical wildcard patterns like "top.mod_*.sub_*" to instance list.
  Use iterative matching through internal_scope_handles().
match_conditions:
  target_name_pattern: ["*", ".*"]
  scope_mode: ["inst_scope"]
---

## When to Use
- User asks for instances matching "top.mod_*" or "*.sub_*"
- User specifies hierarchical path with wildcards
- User asks for instances at specific hierarchy levels with patterns

## Key Concept: Hierarchical Pattern Matching
- Split pattern by "." to get hierarchy levels
- For each level, match instances against the wildcard pattern
- Use internal_scope_handles() to descend into children
- Instance types: npiModule, npiInterface, npiPackage, npiProgram

## Key APIs
- `lang.get_top_inst_list()` - Get top-level instances
- `lang.handle_by_name(name, None)` - Get handle by exact name
- `hdl.internal_scope_handles()` - Get child scopes
- `hdl.name()` - Get short name
- `hdl.full_name()` - Get full hierarchical name
- `hdl.type()` - Check if instance type

## Pattern Matching Helper
```python
def match_pattern(name, pattern):
    '''Match name against wildcard pattern.'''
    if not pattern:
        return True
    if pattern == "*":
        return True
    if pattern.startswith("*") and pattern.endswith("*"):
        return pattern[1:-1] in name
    if pattern.startswith("*"):
        return name.endswith(pattern[1:])
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    return name == pattern
```

## Steps

### Step 1: Parse pattern and define constants
```python
from pynpi import lang

pattern = "top.mod_*.sub_*"  # Example pattern
parts = pattern.split(".")
instance_types = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]
```

### Step 2: Match first level
```python
current_matches = []
first_part = parts[0]

if "*" not in first_part:
    # Exact name
    hdl = lang.handle_by_name(first_part, None)
    if hdl:
        current_matches = [first_part]
else:
    # Wildcard - search top instances
    for top in lang.get_top_inst_list():
        if top.type() in instance_types:
            name = top.name()
            if name and match_pattern(name, first_part):
                current_matches.append(top.full_name())
```

### Step 3: Match remaining levels iteratively
```python
for wildcard in parts[1:]:
    next_matches = []
    for scope_name in current_matches:
        parent_hdl = lang.handle_by_name(scope_name, None)
        if parent_hdl is None:
            continue
        for child in parent_hdl.internal_scope_handles():
            if child.type() not in instance_types:
                continue
            child_name = child.name()
            if child_name and match_pattern(child_name, wildcard):
                full_name = child.full_name()
                if full_name:
                    next_matches.append(full_name)
    current_matches = next_matches
    if not current_matches:
        break
```

### Step 4: Write JSON output
```python
import json
results = [{"identifier": m, "attributes": {"type": "instance"}} for m in current_matches]
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## Example: Match "top.cpu_*.alu"
```python
from pynpi import lang
import json

def match_pattern(name, pattern):
    if pattern == "*":
        return True
    if pattern.startswith("*") and pattern.endswith("*"):
        return pattern[1:-1] in name
    if pattern.startswith("*"):
        return name.endswith(pattern[1:])
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    return name == pattern

pattern = "top.cpu_*.alu"
parts = pattern.split(".")
instance_types = ["npiModule", "npiInterface", "npiPackage", "npiProgram"]

# First level: exact match "top"
current_matches = []
hdl = lang.handle_by_name("top", None)
if hdl:
    current_matches = ["top"]

# Remaining levels
for wildcard in parts[1:]:
    next_matches = []
    for scope_name in current_matches:
        parent_hdl = lang.handle_by_name(scope_name, None)
        if parent_hdl is None:
            continue
        for child in parent_hdl.internal_scope_handles():
            if child.type() not in instance_types:
                continue
            if match_pattern(child.name() or "", wildcard):
                full_name = child.full_name()
                if full_name:
                    next_matches.append(full_name)
    current_matches = next_matches
    if not current_matches:
        break

results = [{"identifier": m, "attributes": {"type": "instance"}} for m in current_matches]
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## IMPORTANT
- Only match instance types: npiModule, npiInterface, npiPackage, npiProgram
- Use internal_scope_handles() to get children, not child instances directly
- Pattern matching is case-sensitive
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
