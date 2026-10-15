---
name: list_signals
description: List all signals (under a specific scope) in the design or FSDB file
target: [verdimaster]
examples:
  - List all signals in this scope
  - List signals under scope "system"
  - List all signals in the design
  - List all signals currently in nWave
  - List signals under scope "system" in waveform
---

## Steps
1. Default: call `DesignAgent(<prompt>)` to extract signals from the design.
   - Exception: if the prompt contains waveform-specific keywords (`nWave`, `waveform`,
     `wave window`, or references to a wave
     group), call `WaveformAgent(<prompt>)` instead and return its result.
2. If `DesignAgent` fails (including "no design is loaded", missing `.daidir`), fall back to `WaveformAgent(<prompt>)`
   to extract signals from the FSDB file.
3. Return the extracted signals to the user.
