# FPGA Domain Knowledge

## Known Failure Patterns

- **BRAM inference coding style**: Xilinx BRAM inference requires a specific coding style — the
  read data output must be registered (synchronous read), and the reset must not be applied to
  the output register. Designs with asynchronous BRAM reads infer LUT RAM instead, consuming
  significantly more LUTs.
- **DSP48 inference blocked by carry-chains**: Arithmetic trees that mix additions and subtractions
  with intermediate carry-chains prevent DSP48 inference. Restructure to keep the full
  multiply-accumulate within a single DSP48 primitive; use `(* use_dsp = "yes" *)` attribute
  to force inference.
- **Prototype frequency target**: Set the FPGA prototype frequency target to 1/3 of the ASIC
  target to account for FPGA fabric overhead. For example, a 1 GHz ASIC target maps to ~333 MHz
  FPGA prototype target. Document the scale factor explicitly in the sign-off report.

## Successful Tool Flags

- `vivado -mode batch -source <script.tcl>` — batch mode for reproducible synthesis/P&R; use
  `set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY none [get_runs synth_1]` to preserve
  hierarchy for debug.
- `nextpnr-xilinx --freq <MHz>` — always set target frequency explicitly; unconstrained nextpnr
  runs do not optimize for timing.
- `openFPGALoader --cable <cable> --verify` — `--verify` reads back bitstream after programming
  to catch flash write failures.

## PDK / Tool Quirks

- **Vivado IP core out-of-context synthesis**: OOC synthesis must complete before top-level
  synthesis or Vivado silently uses stale netlists. Run `synth_ip [get_ips *]` before top-level
  `launch_runs synth_1`.
- **nextpnr-xilinx chip database**: Requires a device-specific chip database built from
  Project X-Ray. Ensure the database matches the exact device part number — mismatches cause
  routing failures that appear as DRC errors.

## Notes

- All performance measurements on the FPGA prototype must be recorded at prototype frequency
  with the ASIC scale factor noted. Reporting FPGA MHz directly as a performance number
  without the scale factor is misleading.
