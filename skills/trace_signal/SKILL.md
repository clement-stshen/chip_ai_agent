---
name: trace_signal
description: Trace the root cause of why a signal has a specific value (including X/unknown values) or the source of a value change. Routes directly to DesignAgent for root cause analysis and X-value debugging. This skill is for value-origin tracing, not signal timing analysis.
target: [verdimaster]
examples:
  - Why does signal A have an X value at 100ns?
  - Trace the unknown value of signal B
  - Find out the root cause of this value change
  - What is the reason of signal C changing value at time 800ns?
  - Trace the signal D and find out the reason why it changed at time 1000ns.
  - Run XRCA on signal E
  - XRCA on signals A, B, C at time 100ns
  - What is the source of X in signal F?
  - Trace X-value in scope top.cpu
  - Find which driver actively controls signal G at time 50ns
---

## Intent Recognition

**Route to this skill (DesignAgent) when the query:**
- Asks for the reason a signal holds a specific value
- Asks for the source or origin of a signal value
- Asks why a signal became X/unknown
- Asks for root cause of a value
- Asks what caused a value to change (seeking the driving source, not the timing)
- Targets a specific signal at a specific time for value analysis
- Targets a scope to identify X-value sources across multiple signals

**Route to WaveformAgent instead when the query:**
- Asks about signal timing or when a signal transitions
- Asks to view or analyze waveforms visually

## Steps

1. Route directly to `DesignAgent` for root cause and X-value tracing.
