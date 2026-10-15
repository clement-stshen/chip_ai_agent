---
name: lang_ports_query
target: [design_exploration]
description: |
  Query ports of a module definition.
  Use port_handles() API to get all ports and their directions.
match_conditions:
  class_types: ["port", "ports", "input", "output", "inout"]
---

## When to Use
- User asks for "ports of module X"
- User asks for "input/output ports"
- User asks about port directions or port lists

## Key APIs
- `lang.find_inst_with_def_wildcard(None, [def_name])` - Find instances of a definition
- `instance.port_handles()` - Get port handles from an instance
- `port.name()` - Get port name
- `port.full_name()` - Get full hierarchical path
- `port.direction()` - Get direction: "input", "output", "inout"

## Steps

### Step 1: Get a representative instance
```python
from pynpi import lang

def_name = "YOUR_MODULE_NAME"  # Replace with actual module name
instances = lang.find_inst_with_def_wildcard(None, [def_name])
if not instances:
    # No instances found
    result = {"total_count": 0, "objects": []}
else:
    inst = instances[0]  # Use first instance as representative
```

### Step 2: Get ports from the instance
```python
results = []
for port in inst.port_handles():
    port_info = {
        "identifier": port.full_name(),
        "attributes": {
            "name": port.name() or "",
            "direction": port.direction() or "",
            "type": "port"
        }
    }
    results.append(port_info)
```

### Step 3: Write JSON output
```python
import json
output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## Example Code
```python
from pynpi import lang
import json

def_name = "cpu"
instances = lang.find_inst_with_def_wildcard(None, [def_name])
results = []

if instances:
    inst = instances[0]
    for port in inst.port_handles():
        results.append({
            "identifier": port.full_name(),
            "attributes": {
                "name": port.name() or "",
                "direction": port.direction() or ""
            }
        })

output = {"total_count": len(results), "objects": results}
with open(OUTPUT_JSON_PATH, "w") as f:
    json.dump(output, f, indent=2)
lang.release_all_handles()
```

## IMPORTANT
- Port direction can be: "input", "output", "inout"
- Use `find_inst_with_def_wildcard` to find instances first, then query ports
- JSON format: `{"total_count": N, "objects": [{"identifier": "...", "attributes": {...}}]}`
