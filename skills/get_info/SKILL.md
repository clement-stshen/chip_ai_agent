---
name: get_info
description: >-
  Retrieve FSDB-level metadata (FSDB version, scale/time unit, min/max time,
  simulator type, completeness flag, sequence/force/glitch flags, packed dump,
  power data, gate technology). Use when the user asks generally about
  "waveform info", "FSDB info", "FSDB metadata", or "what's in the dump".
target: [waveform]
examples:
  - "What's the info of the waveform?"
  - "Show me the FSDB metadata."
  - "What's the FSDB version / time unit / simulator type?"
  - "What's the simulation time range in the dump?"
  - "Get the basic info of <fsdb_file>."
---

## Steps
- 1. Call `get_info()` when the user asks for high-level FSDB metadata
  (version, time unit, min/max time, simulator type, completeness, etc.).
- 2. If the user does NOT name an FSDB file, omit `filename`. The tool
  automatically uses the currently active FSDB in nWave.
- 3. Do NOT ask the user for the FSDB path first. Try `get_info()` with no
  arguments; if no FSDB is loaded the tool returns a clear error message,
  and only then ask the user to load one.
- 4. Do NOT call `set_active_fsdb()` or `get_active_fsdb()` as preparatory
  steps; `get_info()` resolves the active FSDB on its own.
