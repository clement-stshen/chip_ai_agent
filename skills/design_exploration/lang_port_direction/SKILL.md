---
name: lang_port_direction
target: [design_exploration]
description: |
  Handle "input/output signals" queries - actually means ports with direction.
match_conditions:
  has_direction_filter: true
---

## When to Use
User asks for "input signals" or "output signals".

## IMPORTANT
Signals (nets/variables) do NOT have direction in HDL.
Only PORTS have direction.
"Input signals" actually means "input ports".

## Key APIs
- `scope_hdl.port_handles()` - Get ports in scope
- `port_hdl.direction()` - Get port direction

## Steps

### Step 1: Get ports
```python
ports = scope_hdl.port_handles()
```

### Step 2: Filter by direction
```python
# Direction values: "npiInput", "npiOutput", "npiInout"
input_ports = [p for p in ports if p.direction() == "npiInput"]
output_ports = [p for p in ports if p.direction() == "npiOutput"]
inout_ports = [p for p in ports if p.direction() == "npiInout"]
```

## IMPORTANT
- When user says "input signals", search for ports with direction() == "npiInput"
- This is a common user terminology mistake - signals don't have direction
