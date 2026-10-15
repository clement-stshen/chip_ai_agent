---
name: lang_definition_name
target: [design_exploration]
description: |
  Handle requests that reference module/interface definition names.
  Use find_inst_with_def_wildcard to convert definition name to instance names.
match_conditions:
  name_type: ["definition_name"]
---

## When to Use
User provides a definition name instead of full instance name:
- "signals in CPU module"
- "instances of ALU"
- "ports in interface AXI"
- "module foo" or "interface bar"

## Understanding name(), full_name(), def_name()

These are the three key methods for getting names from handles:

Given this code:
```verilog
module top;
  sub sub_inst1();
endmodule

module sub;
  parameter P = 10;
endmodule
```

For the handle of `sub_inst1`:
- `hdl.name()` returns `"sub_inst1"` - the simple/local instance name
- `hdl.full_name()` returns `"top.sub_inst1"` - the full hierarchical path
- `hdl.def_name()` returns `"sub"` - the module definition name

## Distinguishing Name Types in User Request

### 4.a. Definition Name
If user says `"<name> module"`, `"<name> interface"`, `"module <name>"`, `"interface <name>"`, or `"instances of <name>"`:
- It refers to **definition name**
- Use `def_name()` to filter, or use `find_inst_with_def_wildcard()` to find all instances

### 4.b. Full Name (Hierarchical Path)
If user provides a path with dots (e.g., `"top.sub.inst"`):
- It is a **full name**
- Use `handle_by_name()` directly, or filter by `full_name()`

### 4.c. Simple Instance Name
If user mentions `"instance named <name>"` or `"instance <name>"` without dots:
- It refers to **simple instance name**
- Use `name()` to filter

### 4.d. When in Doubt
- Paths with `.` are full names
- `module/interface/package/program` followed by a name indicates definition name
- Standalone identifiers are instance names

## Key APIs
- `lang.find_inst_with_def_wildcard(start_scope, [def_name])` - Find instances matching definition name
  - start_scope: starting scope (None for whole design)
  - Returns list of instance handles matching the definition name
- `hdl.name()` - Get simple instance name (e.g., "sub_inst1")
- `hdl.full_name()` - Get full hierarchical name (e.g., "top.sub_inst1")
- `hdl.def_name()` - Get definition/cell name (e.g., "sub")

## Understanding name(), full_name(), def_name()

**Example design:**
```verilog
module top;
  sub sub_inst1();
endmodule

module sub;
  parameter P = 10;
endmodule
```

**For the handle of sub_inst1:**
- `name()` returns `"sub_inst1"` (simple instance name)
- `full_name()` returns `"top.sub_inst1"` (full hierarchical path)
- `def_name()` returns `"sub"` (module definition name)

## Distinguishing Name Types

### Rule 1: Paths with dots are full names
- `"top.sub.inst"` → full_name, use `handle_by_name()` directly
- `"a.b.c.signal"` → full_name, use `handle_by_name()` directly

### Rule 2: "module X", "interface X", "instances of X" indicate definition names
- `"signals in module CPU"` → CPU is definition name
- `"instances of ALU"` → ALU is definition name
- `"ports of interface AXI"` → AXI is definition name
- Use `find_inst_with_def_wildcard()` to find instances

### Rule 3: "instance named X" without dots is simple name
- `"instance named cpu_core"` → simple name, filter by `name()`
- Traverse and check `hdl.name() == "cpu_core"`

### Rule 4: When in doubt
- Paths with '.' → full names → `handle_by_name()`
- "module/interface/package/program" followed by name → definition name → `find_inst_with_def_wildcard()`
- Standalone identifiers → instance names → filter by `name()`

## Steps

### Step 1: Identify definition name
Definition names are module/interface/package/program names, NOT hierarchical paths.
- "CPU module" → definition name is "CPU"
- "instances of ALU" → definition name is "ALU"
- Paths with dots like "top.cpu" are full names, NOT definition names

### Step 2: Find instances with definition name
```python
instances = lang.find_inst_with_def_wildcard(None, ["<definition_name>"])
```
- Pass `None` as start_scope to search whole design
- Returns list of instance handles

### Step 3: Use instance full_name for further operations
For each found instance:
```python
for inst in instances:
    inst_full_name = inst.full_name()
    # Now use inst_full_name with handle_by_name or hier_tree_trv
```

### Step 4: Handle multiple instances
If multiple instances match the definition:
- Process each instance separately
- Or inform user about multiple matches

## Keyword Search: Module vs Instance (CRITICAL)

### Distinguishing "module" vs "module instance"

| User Phrase | What They Mean | API to Use |
|-------------|----------------|------------|
| "module X", "module name X", "modules containing X" | Module definition name | `def_name()` |
| "module instance X", "instances containing X" | Instance path or instance name | `full_name()` or `name()` |
| "instance named X" (short name) | Simple instance name | `name()` |
| "instances with X in path" (full path) | Full hierarchical path | `full_name()` |

### Rule: "module" = definition, "module instance" = instance

- **"modules containing ALU"** → check `def_name()` for "ALU"
- **"module instances containing ALU"** → check `full_name()` for "ALU" 
- **"instance named cpu_core"** → check `name()` for "cpu_core"

### Code Patterns

**For "modules containing X" (definition name search):**
```python
for scope in internal_scopes:
    if is_instance(scope):
        def_name = scope.def_name()
        if def_name and keyword in def_name:
            if not def_name.startswith("$"):  # Filter UPF structures
                result.append(scope)
```

**For "module instances containing X" (hierarchical path search):**
```python
for scope in internal_scopes:
    if is_instance(scope):
        full_name = scope.full_name()
        if full_name and keyword in full_name:
            result.append(scope)
```

**For "instance named X" (simple name search):**
```python
for scope in internal_scopes:
    if is_instance(scope):
        simple_name = scope.name()
        if simple_name and keyword in simple_name:
            result.append(scope)
```

### IMPORTANT
- "module" alone refers to **definition** → use `def_name()`
- "module instance" refers to **instance** → use `full_name()` or `name()`
- Filter out UPF power structures (def_name starting with `$`) when searching definitions

## IMPORTANT
- `handle_by_name()` and `hier_tree_trv()` do NOT accept definition names
- Always convert definition name to full instance name first
- `find_inst_with_def_wildcard` accepts wildcards in definition name (e.g., "CPU*")
- For keyword search, check `def_name()` not `full_name()` to avoid path matching
- Filter out UPF power structures (def_name starting with `$`)
