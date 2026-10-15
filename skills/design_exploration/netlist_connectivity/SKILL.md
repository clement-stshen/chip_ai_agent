---
name: netlist_connectivity
target: [design_exploration]
description: |
  Connectivity analysis in Netlist library.
  Includes signal-to-signal paths, equivalent nets, fan-in/out.
match_conditions:
  is_connectivity_query: true
---

## When to Use
User asks about connectivity between objects:
- "Is pin A connected to pin B"
- "Equivalent nets of signal X"
- "Fan-in of signal Y"
- "Connection path between net A and net B"

## Key APIs
- `netlist.sig_to_sig_conn_list(from_net, to_net)` - Find connection path
- `net.to_sig_conn_list(other_net)` - Alternative for connection path
- `net.eq_net_list()` or `net.equivalent_net_list()` - Get equivalent nets
- `net.fan_in_reg_list()` - Get fan-in registers
- `net.fan_out_reg_list()` - Get fan-out registers

## Pattern: Check Pin Connectivity

```python
from pynpi import netlist

pin1_name = "top.u_a.data_out[7:0]"
pin2_name = "top.u_b.data_in[7:0]"

pin1 = netlist.get_instport(pin1_name)
pin2 = netlist.get_instport(pin2_name)

if pin1 is not None and pin2 is not None:
    net1 = pin1.connected_net()
    net2 = pin2.connected_net()

    if net1 is not None and net2 is not None:
        conn_list = net1.to_sig_conn_list(net2)
        if len(conn_list) > 0:
            result["objects"].append({
                "identifier": f"{pin1_name} <-> {pin2_name}",
                "attributes": {
                    "connected": True,
                    "path_count": len(conn_list)
                }
            })
```

## Pattern: Equivalent Nets

```python
net_name = "top.clock"
net = netlist.get_net(net_name)

if net is not None:
    equiv_nets = net.eq_net_list()
    for eq_net in equiv_nets:
        result["objects"].append({
            "identifier": eq_net.full_name(),
            "attributes": {
                "equivalent_to": net_name
            }
        })
```

## Pattern: Fan-In Analysis

```python
signal_name = "top.data_out"
net = netlist.get_net(signal_name)

if net is not None:
    # Get fan-in registers
    fan_in_regs = net.fan_in_reg_list()
    for reg in fan_in_regs:
        result["objects"].append({
            "identifier": reg.full_name(),
            "attributes": {
                "relation": "fan_in_of",
                "target": signal_name
            }
        })
```

## Pattern: Fan-Out Analysis

```python
net = netlist.get_net(signal_name)
if net is not None:
    fan_out_regs = net.fan_out_reg_list()
    for reg in fan_out_regs:
        result["objects"].append({
            "identifier": reg.full_name(),
            "attributes": {
                "relation": "fan_out_of",
                "target": signal_name
            }
        })
```

## CRITICAL RULES

1. **All connectivity functions return lists or None** - always check
2. **Use `to_sig_conn_list` for path finding** between two nets
3. **Fan-in/out functions work on NetHdl** - get net handle first
4. **Equivalent nets include the original net** in the list
