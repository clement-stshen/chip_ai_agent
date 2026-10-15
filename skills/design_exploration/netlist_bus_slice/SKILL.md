---
name: netlist_bus_handling
target: [design_exploration]
description: |
  Handle bus bits, slices, and parent relationships in Netlist library.
match_conditions:
  has_bus_query: true
---

## When to Use
User asks about:
- Individual bits of a bus
- Part-select / slices of a bus
- Parent bus of a bit/slice

## Key APIs
- `bus_hdl.index(i)` - Get bit-select pseudo net handle
- `bus_hdl.range(left, right)` - Get part-select pseudo net handle
- `bit_hdl.parent()` - Get parent bus handle

## Bus Operations

### Getting a bit from a bus
```python
# Get bus handle first
bus = netlist.get_net("top.data[7:0]")  # Returns npiNlDeclNet

# Get bit 3
bit3 = bus.index(3)  # Returns npiNlPseudoNet like 'top.data[7:0]#[3]'
```

### Getting a slice from a bus
```python
# Get bits 7 to 4 (a nibble)
nibble = bus.range(7, 4)  # Returns npiNlPseudoNet like 'top.data[7:0]#[7:4]'
```

### Getting parent from a bit/slice
```python
# Recover the original bus from a bit or slice
bus_parent = bit3.parent()  # Returns the original npiNlDeclNet 'top.data[7:0]'
```

## Handle Types

| Operation | Input Type | Output Type |
|-----------|-----------|-------------|
| get_net("bus[7:0]") | - | npiNlDeclNet |
| bus.index(i) | npiNlDeclNet | npiNlPseudoNet |
| bus.range(l,r) | npiNlDeclNet | npiNlPseudoNet |
| bit.parent() | npiNlPseudoNet | npiNlDeclNet |

## Full Example

```python
from pynpi import netlist

# Get bus net
bus = netlist.get_net("top.data[7:0]")
if bus is None:
    print("Bus not found")
else:
    print(f"Bus: {bus.full_name()}")  # top.data[7:0]
    print(f"Bus type: {bus.type()}")  # npiNlDeclNet

    # Get bit 3
    bit3 = bus.index(3)
    print(f"Bit 3: {bit3.full_name()}")  # top.data[7:0]#[3]
    print(f"Bit type: {bit3.type()}")  # npiNlPseudoNet

    # Get nibble [7:4]
    nibble = bus.range(7, 4)
    print(f"Nibble: {nibble.full_name()}")  # top.data[7:0]#[7:4]

    # Recover parent from bit
    parent = bit3.parent()
    print(f"Parent: {parent.full_name()}")  # top.data[7:0]
```

## IMPORTANT
- `get_inst()`, `get_port()`, `get_instport()`, `get_net()` require CONCRETE names, not wildcards
- For wildcard patterns, enumerate objects (via traversal or local lists) and filter by name
- Pseudo nets (from index/range) have names with '#' suffix indicating the bit/slice selection
- Always check for None before using returned handles
