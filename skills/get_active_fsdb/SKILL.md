---
name: get_active_fsdb
description: Check or retrieve which FSDB file is currently active (loaded) in nWave.
target: [waveform]
examples:
  - Check if <fsdb_name> is loaded.
  - Which FSDB is currently active?
  - What waveform file is open?
  - Is <fsdb_name> loaded in nWave?
  - Get the current active FSDB.
---

## Steps
- 1. Use `get_active_fsdb()` when the prompt asks to check, query, or retrieve which FSDB file is currently active or loaded in nWave.
- 2. This function takes no arguments. It returns the name of the currently active FSDB, or reports that no FSDB is loaded.
- 3. Do NOT use `set_active_fsdb()` for check/query prompts — that function opens or switches FSDBs.
