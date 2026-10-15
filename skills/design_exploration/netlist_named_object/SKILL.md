---
name: netlist_named_object
target: [design_exploration]
description: |
  Get details/connectivity of specific named Netlist objects.
  Use get_inst/get_port/get_net to get handles directly.
match_conditions:
  traverse_mode: ["named_object"]
---

## When to Use
User requests involve getting details or connectivity of specific named objects:
- "Is instport A connected to instport B"
- "Equivalent nets of net X"
- "Unconnected ports in instance X"
- "Connectivity between net A and net B"

## Key APIs
- `netlist.get_inst(hier_name)` - Get instance handle
- `netlist.get_port(hier_name)` - Get port handle
- `netlist.get_instport(hier_name)` - Get instance port handle
- `netlist.get_net(hier_name)` - Get net handle
- `netlist.get_actual_net(hier_name)` - Get actual net handle

## CRITICAL: None Checking

**All member functions that return handles will return None if the object does not exist.**
You MUST check for None before using the returned value.

```python
# BAD - will crash if object doesn't exist
inst = netlist.get_inst("top.module1")
children = inst.inst_list()  # Crash if inst is None!

# GOOD - always check for None
inst = netlist.get_inst("top.module1")
if inst is None:
    print("Instance not found")
else:
    children = inst.inst_list()
```

## Common Operations

### Get instance children (with None check):
```python
inst = netlist.get_inst("top.module1")
if inst is not None:
    children = inst.inst_list()  # Child instances
    ports = inst.port_list()     # Ports
    nets = inst.net_list()       # Nets
```

### Check connectivity (with None check):
```python
port = netlist.get_port("top.module1.clk")
if port is not None:
    connected_net = port.connected_net()
    if connected_net is not None:
        print(f"Connected to: {connected_net.full_name()}")
```

### Get equivalent nets:
```python
net = netlist.get_net("top.data")
if net is not None:
    equiv_nets = net.equivalent_net_list()
```

### Signal to signal connectivity:
```python
# Use NetHdl.to_sig_conn_list() or netlist.sig_to_sig_conn_list()
if net1 is not None and net2 is not None:
    conn_list = net1.to_sig_conn_list(net2)
```

## IMPORTANT
- `get_inst()`, `get_port()`, `get_instport()`, `get_net()` require CONCRETE names, not wildcards
- For wildcard patterns, traverse the design and filter by `hdl.full_name()` or `hdl.name()`
- Always check return values for None before accessing member functions
