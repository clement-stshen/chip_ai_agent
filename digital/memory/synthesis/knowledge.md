# Synthesis Domain Knowledge

## Known Failure Patterns

- **Genus set_max_area alone does not close WNS**: In Cadence Genus, `set_max_area 0` alone
  does not drive timing closure. WNS violations persist if timing constraints are not applied
  before area optimization. Always set timing constraints (`create_clock`, `set_input_delay`,
  `set_output_delay`) before `compile_ultra` — area optimization runs automatically within the
  timing budget.
- **Scan chain false paths before compile_ultra**: Scan chain false paths must be declared in the
  SDC (`set_false_path -from [get_ports scan_in] -to [get_ports scan_out]`) before `compile_ultra`.
  Declaring them after causes Fusion Compiler to re-optimize scan paths, breaking chain continuity
  and requiring LEC re-run.

## Successful Tool Flags

- `dc_shell -f <script.tcl> -output_log_file <log>` — always capture the log; `check_design`
  warnings about unresolved references are the most common root cause of synthesis failures.
- `genus -legacy_ui -files <script.tcl>` — `--legacy_ui` mode is more stable for scripted flows
  than the default UI mode; avoids interactive prompts that hang batch jobs.

## PDK / Tool Quirks

- **`ultra` effort past 2× loop-backs**: `compile_ultra` with `ultra` effort rarely closes WNS
  past 2 loop-back iterations — further effort yields < 1% improvement at 3–5× runtime cost.
  Switch to targeted path optimization (`compile_ultra -only_design_rule` + `optimize_registers`)
  after 2 failed `compile_ultra` runs.

## Notes

- LEC must be run after every netlist change — not just at signoff. A single unverified netlist
  change that reaches PD and fails LEC there costs a full PD re-run.
