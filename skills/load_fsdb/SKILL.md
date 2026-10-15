---
name: load_fsdb
description: Load the specific FSDB file into Verdi nWave. Only use when the user explicitly asks to load, import, or open an FSDB. Do NOT use for analytical queries that merely reference an FSDB by name (e.g. "show value of signal X in Y.fsdb", "get transitions in Z.fsdb").
target: [verdimaster]
examples:
  - Import run.fsdb
  - Load the waveform file rtl.fsdb
---

## Steps
1. Call `WaveformAgent(<prompt>)` to load the FSDB file into Verdi nWave
