# Architecture Domain Knowledge

## Known Failure Patterns

- **Incomplete spec → HIGH risk_assessment**: A `risk_assessment` outcome of HIGH on schedule
  almost always means the input spec is missing corner-case requirements. Request spec clarification
  before iterating on arch_exploration — additional exploration iterations will not resolve an
  under-specified schedule risk.
- **McPAT area estimates**: ±30% without technology calibration. Do not use raw McPAT numbers for
  final area budgets; apply technology scaling factor from known tape-out data or designer input.
- **gem5 OOO branch predictor**: Out-of-order gem5 models need branch predictor tuning to get within
  15% of silicon IPC. Default LTAGE parameters are often mismatched for deeply embedded workloads —
  tune `BTBEntries`, `RASSize`, and `numThreads` before reporting throughput numbers.

## Successful Tool Flags

- `gem5` in-order models (`MinorCPU`) are within 15% of silicon for in-order pipelines with no
  branch-predictor tuning needed.
- `mcpat --inorder` mode gives more accurate area estimates for in-order designs than the default
  out-of-order configuration.
- `cacti -cache_size <N> -block_size <B> -associativity <A>` — always specify all three to avoid
  CACTI defaulting to parameters that do not match the design.

## PDK / Tool Quirks

- **Platform Architect**: requires licence server ping at startup; if `spec_analysis` hangs, check
  `LM_LICENSE_FILE` and run `lmstat -a` before retrying.
- **VSP (Cadence)**: TLM model import fails silently if the `.so` is compiled with a different GCC
  ABI than the VSP runtime — rebuild with `--std=c++14` and matching `-fabi-version`.

## Notes

- McPAT and CACTI estimates should always be presented with explicit uncertainty bounds in the
  microarchitecture document — do not round to "nice" numbers without noting the model error.
