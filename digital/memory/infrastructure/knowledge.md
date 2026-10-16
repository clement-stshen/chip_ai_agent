# Infrastructure Domain Knowledge

Tracking is **opt-in** (`pipeline_config.track_infrastructure: true` or `--track-memory`) and
records in `experiences.jsonl` are **environment-keyed** (`host` / `os` / `arch`). When reading
this file, prefer entries whose environment matches the current host — tool versions and quirks
are machine-specific. Lockfiles remain the primary source of truth for exact versions; this
memory captures the *debugging cost* of mismatches, not the canonical version pin.

## Known Failure Patterns

- **Wrong licensed module remains active**: A stale shell can resolve an unintended EDA version.
  Record the loaded vendor module and exact executable path with each run; request a fresh site
  module load rather than changing binaries or installing a replacement.
- **EDA tool presence mistaken for license availability**: A binary in `PATH` does not prove a
  successful license checkout. Confirm license availability only through the authorized vendor
  tool invocation and preserve its exact error output.

## Environment Notes

- Host compiler, shell, and Python resolution may be recorded separately from EDA inventory.
- Never create local EDA installations or alternate-tool fallbacks from this agent.

## Notes

- This domain is design-independent: `design_name` is usually `null`. Records are differentiated
  by the `environment` fingerprint, not by design.
- `key_metrics.tool_versions` is the primary value-add — a per-tool version map captured at
  `environment_validation`. Comparing it across runs surfaces the exact tool that changed when a
  previously-passing flow starts failing.
