---
name: set_active_fsdb
description: Open/import/load a waveform (FSDB) and set it as the active FSDB in nWave.
target: [waveform]
examples:
  - Open fsdb <fsdb_name>.
  - Open waveform <fsdb_name>.
  - Load <fsdb_name>.
  - Load <fsdb_name> as active waveform.
  - Import <fsdb_name>.
  - Switch to <fsdb_name>.
  - Open fsdb <fsdb_name> in a new nWave window.
---

## Steps
- 1. Use `set_active_fsdb()` when the prompt asks to open/load/import a waveform file or switch the active FSDB.
- 2. Set `fsdb_name=<fsdb_name>` exactly as the user provided (the name may or may not include a .fsdb extension).
- 3. If the prompt asks to open in a new window, set `new_window=True`; otherwise keep default.
