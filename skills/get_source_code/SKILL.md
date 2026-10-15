---
name: get_source_code
description: |
  Retrieve source location from module instance/definition first, then read/grep the real HDL file.
  Use this when user wants RTL implementation details, logic explanation, or code patterns.
target: [design]
examples:
  - "Show me the source code of <module>."
  - "Get the RTL code for <instance>."
  - "Print the verilog code of <module_definition>."
  - "What does module <module> look like?"
  - "Show me how <module> is implemented."
---

## Steps
- 1. Identify whether the user provides a module instance name or module definition name.
- 1.a. If it's a hierarchical path (e.g., top.sub_inst), call `get_code_by_module_instance()` to get location (file path, begin line, end line).
- 1.b. If it's a definition name (e.g., sub), call `get_code_by_module_definition()` to get location (file path, begin line, end line).
- 2. Use `read_files()` to read the returned source file around the location range.
- 2.a. Start with the returned begin/end lines and expand context if needed.
- 3. If user asks for specific syntax/pattern (e.g., always/case/reset/assignment), call `grep_files()` on that source file.
- 4. Summarize and explain the implementation based on read/grep results, instead of returning only location text.
