---
name: lang_interface_binding
target: [design_exploration]
description: |
  Finding interface bindings (bind statements in SystemVerilog).
  Bind instances have scope.bind() == 1.
match_conditions:
  target_object_class: ["interface", "binding", "bind"]
---

## Interface Binding Search

When searching for interface bindings like "find SI interface bindings with apb_if":

**CRITICAL**: Do NOT use `find_inst_with_def_wildcard` for bind queries.
This API finds interface INSTANCES, not bind INSTANCES.

## Correct Pattern for Interface Bindings

The staged flow provides module instances as representatives. You must search INSIDE
each module to find interface bindings. Interface bindings are interface instances
with `bind() == 1`.

To find bindings, you must:
1. Iterate through scope_list (module instances from SCOPE_FILE_PATH)
2. BFS through `internal_scope_handles()` within each module
3. For each child, check `child.type() == "npiInterface"`
4. Check `child.bind() == 1` (indicates bind instance, not regular instance)
5. Check `child.def_name()` matches the bound interface (e.g., "SI")
6. Check parent scope `def_name()` matches target (e.g., "apb_if")

**Example: Find SI interface bindings with apb_if**
```python
from collections import deque
from pynpi import lang

def is_instance(handle):
    return handle.type() in ["npiModule", "npiInterface", "npiPackage", "npiProgram"]

result = {"total_count": 0, "objects": []}

for scope_name in scope_list:
    module_hdl = lang.handle_by_name(scope_name, None)
    if module_hdl is None:
        continue

    # BFS to search INSIDE module for interface bindings
    bfs_queue = deque([module_hdl])
    while bfs_queue:
        current = bfs_queue.popleft()
        for child in current.internal_scope_handles():
            child_type = child.type()
            # Found an interface - check if it's a binding
            if child_type == "npiInterface":
                if child.bind() == 1:  # This is a bind instance
                    def_name = child.def_name()
                    parent_scope = child.scope_handle()
                    parent_def_name = parent_scope.def_name() if parent_scope else None
                    # Filter: SI interface bindings within apb_if
                    if def_name == "SI" and parent_def_name == "apb_if":
                        full_name = child.full_name()
                        name = child.name()
                        identifier = full_name if full_name else (f"{name} ({child.file()}:{child.line_no()})" if name else f"{child.file()}:{child.line_no()}")
                        result["objects"].append({
                            "identifier": identifier,
                            "source_scope": scope_name,
                            "attributes": {
                                "def_name": def_name,
                                "parent_def_name": parent_def_name,
                                "bind": child.bind()
                            }
                        })
            # Continue BFS but skip into module/interface/package/program instances
            elif not is_instance(child):
                bfs_queue.append(child)
```

## Key APIs

- `scope.bind()` - Returns 1 if this is a bind instance, 0 if regular instance
- `scope.def_name()` - Returns the definition name of the interface
- `scope.scope_handle()` - Returns the parent scope handle

## WRONG Pattern (do NOT do this)

```python
# WRONG - finds interface INSTANCES, not bind instances
instances = lang.find_inst_with_def_wildcard(None, ["apb_if"])

# WRONG - finds all SI instances, not just bindings
instances = lang.find_inst_with_def_wildcard(None, ["SI"])

# WRONG - checks if scope_list item itself is interface (staged flow provides modules)
for scope_name in scope_list:
    hdl = lang.handle_by_name(scope_name, None)
    if hdl.type() == "npiInterface" and hdl.bind() == 1:
        # This will never match because scope_list contains module instances
        ...
```

## Important

- `bind` statements create interface instances inside other scopes
- These are different from regular interface instances
- Only `scope.bind() == 1` indicates a bind instance
- The staged flow provides module instances - you must BFS inside them to find interfaces
