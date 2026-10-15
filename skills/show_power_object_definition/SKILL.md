---
name: show_power_object_definition
description: |
  Show the source code definition of a power object and navigate to it in the GUI.
  Gets the UPF file location and reads the source code around the definition.
  Use this skill when:
  - User asks to "show definition" of a power object
  - User asks for "source code" of a power object
  - User says "jump to", "go to", or "navigate to" a power object definition
  - User wants to see where a power object is defined in UPF
  Do NOT use when:
  - User only wants information about the power object (use report tools directly)
  - User wants to search for power objects by pattern (use search_power_objects skill)
  Keywords: show definition, source code, jump to, go to, navigate, where defined, UPF source.
target: [power]
examples:
  - "Show the definition of power domain top/PD_A"
  - "Show me the source code for power domain PD_TOP"
  - "Jump to the definition of supply set SS_VDD"
  - "Where is power switch SW_CPU defined?"
  - "Go to the UPF source for isolation strategy ISO_A"
  - "Show the definition of retention strategy RET_CPU"
---

## Workflow

When user asks to show definition or source code of a power object:

1. **Identify the power object type and name**:
   - Power domain: names like PD_*, or user says "power domain"
   - Supply set: names like SS_*, or user says "supply set"
   - Supply net: names like VDD*, VSS*, or user says "supply net"
   - Supply port: user says "supply port"
   - Power switch: names like SW_*, or user says "power switch"
   - PST: user says "power state table" or "PST"
   - Isolation strategy: names like ISO_*, or user says "isolation"
   - Retention strategy: names like RET_*, or user says "retention"
   - Level shifter strategy: user says "level shifter"

2. **Get the Definition Location** (File and Line):
   Call the appropriate report tool based on the power object type:
   - `report_power_domain` for power domains
   - `report_supply_set` for supply sets
   - `report_supply_net` for supply nets
   - `report_supply_port` for supply ports
   - `report_power_switch` for power switches
   - `report_power_state_table` for PSTs
   - `report_isolation_strategy` for isolation strategies
   - `report_retention_strategy` for retention strategies

   The report will return "Definition Location" with:
   - File: path to the UPF file
   - Line: line number where the object is defined

3. **Handle object not found**:
   If the power object is not found:
   - Call `get_current_selected_scope()` to get the currently selected scope
   - Prepend the scope to the object name and retry (e.g., "PD_A" → "top/PD_A")
   - If still not found, call `get_power_top()` and prepend design top scope

4. **Read the source code**:
   Use `read_files` tool to read the UPF source code:
   - Set `file_path` to the UPF file path from the report
   - Set `start_line` to definition line - 5 (to show context before)
   - Set `end_line` to definition line + 15 (to include the full definition)

5. **Jump to definition in GUI**:
   Call `jump_to_power_object_definition` with the power object name to navigate the GUI to the definition location.

## Examples

**Example 1: "Show the definition of power domain top/PD_A"**
1. Identify: power domain, name = "top/PD_A"
2. Call `report_power_domain(full_name="top/PD_A")`
   → Returns: File: /path/to/design.upf, Line: 18
3. Call `read_files(file_path="/path/to/design.upf", start_line=13, end_line=33)`
   → Returns source code around the definition
4. Call `jump_to_power_object_definition(name="top/PD_A")`
   → GUI navigates to the definition
5. Return the source code to user

**Example 2: "Show me the source code for power switch SW_CPU"** (no full path)
1. Identify: power switch, name = "SW_CPU"
2. Call `report_power_switch(full_name="SW_CPU")`
   → Returns error (not found)
3. Call `get_current_selected_scope()` → {"selected_scopes": ["system/i_cpu"]}
4. Retry: `report_power_switch(full_name="system/i_cpu/SW_CPU")`
   → Returns: File: /path/to/power.upf, Line: 45
5. Call `read_files(file_path="/path/to/power.upf", start_line=40, end_line=60)`
6. Call `jump_to_power_object_definition(name="system/i_cpu/SW_CPU")`
7. Return the source code to user

**Example 3: "Jump to the definition of isolation strategy ISO_A"**
1. Identify: isolation strategy, name = "ISO_A"
2. Call `get_current_selected_scope()` → {"selected_scopes": ["top"]}
3. Call `report_isolation_strategy(full_name="top/ISO_A")`
   → Returns: File: /path/to/upf/isolation.upf, Line: 12
4. Call `read_files(file_path="/path/to/upf/isolation.upf", start_line=7, end_line=27)`
5. Call `jump_to_power_object_definition(name="top/ISO_A")`
6. Return the source code to user

## Key Rules

- **ALWAYS call jump_to_power_object_definition**: This is required for any "show definition" request
- **Read source code context**: Include 5 lines before and 15 lines after the definition line
- **Handle missing scope**: If object not found, try prepending the selected scope or design top
- **Report tool mapping**:
  * Power domain → `report_power_domain`
  * Supply set → `report_supply_set`
  * Supply net → `report_supply_net`
  * Supply port → `report_supply_port`
  * Power switch → `report_power_switch`
  * PST → `report_power_state_table`
  * Isolation → `report_isolation_strategy`
  * Retention → `report_retention_strategy`
