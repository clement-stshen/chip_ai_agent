---
name: netlist_port_query
target: [design_exploration]
description: |
  Query port properties in Netlist library.
  Includes unconnected ports, clock ports, reset ports, etc.
match_conditions:
  is_port_query: true
---

## When to Use
User asks about port properties or connectivity:
- "Find unconnected ports"
- "List clock ports"
- "Show reset ports"
- "Input/output port analysis"

## Key APIs
- `inst.port_list()` - Get all ports of an instance
- `port.connected_pin()` - Get connected instport (None if unconnected)
- `port.connected_net()` - Get connected net
- `port.port_type()` - Get port type (e.g., npiNlClockPort)
- `port.direction()` - Get direction (input/output/inout)

## Port Types
Common port_type() values:
- `npiNlClockPort` - Clock port
- `npiNlResetPort` - Reset port
- `npiNlDataPort` - Data port
- `npiNlRegisteredPort` - Registered (FF) output port
- `npiNlFSMControlPort` - FSM control port
- `npiNlFSMOutputPort` - FSM output port

## Pattern: Unconnected Ports

```python
for scope_name in scope_list:
    inst = netlist.get_inst(scope_name)
    if inst is None:
        continue

    for port in inst.port_list():
        connected = port.connected_pin()
        if connected is None:
            result["objects"].append({
                "identifier": port.full_name(),
                "attributes": {
                    "connected": False,
                    "direction": port.direction()
                }
            })
```

## Pattern: Clock Ports

```python
for scope_name in scope_list:
    inst = netlist.get_inst(scope_name)
    if inst is None:
        continue

    for port in inst.port_list():
        if port.port_type() == "npiNlClockPort":
            net = port.connected_net()
            result["objects"].append({
                "identifier": port.full_name(),
                "attributes": {
                    "port_type": "npiNlClockPort",
                    "connected_net": net.full_name() if net else None
                }
            })
```

## Pattern: Port with InstPort Connection

For checking instance port connections:
```python
inst = netlist.get_inst(scope_name)
if inst is not None:
    for instport in inst.instport_list():
        port_type = instport.port_type()
        net = instport.connected_net()
        # ... process ...
```

## CRITICAL: None Checking

```python
# Always check before accessing properties
port = inst.port_list()[0] if inst.port_list() else None
if port is not None:
    net = port.connected_net()
    if net is not None:
        print(net.full_name())
```
