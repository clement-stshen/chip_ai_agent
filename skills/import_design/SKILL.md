---
name: import_design
description: Import/load a design database (simv.daidir or *.daidir) into Verdi for analysis.
target: [design]
examples:
  - "Import design simv.daidir"
  - "Load design database ./build/simv.daidir"
  - "Open the design at /project/rtl/top.daidir"
  - "Load design.daidir"
  - "Import the design database simv.daidir"
---

## Path Handling
- Extract the literal path string from the user's request (e.g., 'simv.daidir', './build/design.daidir', '/project/top.daidir').
- Use the path exactly as the user provides it. Relative paths (without leading '/') refer to the current working directory.
- If the user's request contains a wildcard pattern, ask them to specify the exact directory path.

## Steps
- 1. Extract the path string from the user's request following the path handling guidelines above.
- 2. Verify the path ends with .daidir extension (this tool only supports .daidir design databases).
- 3. Call `import_design()` with the design_folder parameter set to the exact path from step 1.
- 4. Report success or failure to the user. If failure, provide the reason.
- 5. Note: For waveform files (.fsdb, .vcd, .vpd), inform the user to use the Waveform Agent instead.
