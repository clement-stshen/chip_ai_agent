---
name: reload_design
description: |
  Reload all currently loaded data (design database and waveforms) and refresh all Verdi windows that are already opened. Users intend to reload the design after making changes to the design.
target: [design]
examples:
  - "Reload the design."
  - "Refresh the current design."
  - "Reload all data."
  - "The design files have been updated, reload them."
  - "Reload design and waveforms."
---

## Steps
- 1. Verify that a design is already loaded (optionally call `check_if_design_loaded()` first).
- 2. Call `reload_design()` to refresh all currently loaded data.
- 3. Report success or failure to the user.
- 4. Note: This is for RELOADING existing data, not for initial loading of new files.
