---
name: explain_design_from_source
description: |
  For explain/describe style design queries (design-content understanding, not explicit object listing),
  first get source location by module instance/definition, then read/grep the HDL file to produce explanation.
target: [design]
examples:
  - "Explain this module implementation."
  - "Describe how module <module_definition> works."
  - "Please describe the datapath in <module_instance>."
  - "Explain the control logic of <module>."
  - "Describe this design block in detail."
---

## When to Use
- Use this skill for explain/describe/introduction style queries that ask for design content understanding.
- Do not use this skill when user asks for strict object search/count (those belong to `structure_exploration`).

## Steps
- 1. Determine the target module instance or module definition from user query/context.
- 2. Call `get_code_by_module_instance()` or `get_code_by_module_definition()` first to get location.
- 3. From the returned location, call `read_files()` on the source file and read the implementation range with enough context.
- 4. If explanation needs focused evidence (FSM, reset path, always block, case/if tree, assignment path), call `grep_files()` on the same source file to collect key lines.
- 5. Build explanation from source evidence:
- 5.a. Briefly summarize module purpose.
- 5.b. Explain key logic blocks (combinational vs sequential, state/update logic, interfaces).
- 5.c. Cite important conditions/signals found by read/grep.
- 6. If returned location cannot be resolved, report the failure and ask user for a clearer instance/definition name.
