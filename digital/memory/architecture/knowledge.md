# Architecture Domain Knowledge

## Known Failure Patterns

- **Incomplete spec → HIGH risk_assessment**: A `risk_assessment` outcome of HIGH on schedule
  almost always means the input spec is missing corner-case requirements. Request spec clarification
  before iterating on arch_exploration — additional exploration iterations will not resolve an
  under-specified schedule risk.

## PDK / Tool Quirks

- **Platform Architect**: requires licence server ping at startup; if `spec_analysis` hangs, check
  `LM_LICENSE_FILE` and run `lmstat -a` before retrying.
- **VSP (Cadence)**: TLM model import fails silently if the `.so` is compiled with a different GCC
  ABI than the VSP runtime — rebuild with `--std=c++14` and matching `-fabi-version`.

## Notes

- Analytical estimates should always include explicit uncertainty bounds in the
  microarchitecture document; do not round to "nice" numbers without noting model error.
