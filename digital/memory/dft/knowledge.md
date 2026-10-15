# DFT Domain Knowledge

## Known Failure Patterns

- **Scan DRC errors from clock gating cells**: The most common source of scan DRC errors is clock
  gating cells without test control logic. Add test-enable (`TE`) ports to all ICG cells and verify
  they connect to the scan enable network before running `scan_insertion`.
- **ATPG coverage below 95%**: Coverage below 95% after full ATPG is almost always caused by
  unpowered logic domains or missing tie-offs on unused inputs. Audit power domain boundaries and
  ensure all unused inputs are tied high or low before retrying ATPG.
- **BIST MISR false-pass**: MISR polynomial selection directly affects the probability of a
  false-pass (aliasing). Use a primitive polynomial of degree equal to the MISR register width.
  Default TetraMAX/Modus MISR polynomials are safe; custom implementations must be verified.

## Successful Tool Flags

- `tmax -scan_chain_length <N>` — setting explicit chain length prevents TetraMAX from creating
  excessively long chains that degrade test application time.
- `modus -coverage_model full_fault` — enables both SAF and TDF coverage tracking in a single run;
  avoids a separate TDF run later in the flow.
- `tessent -shell -dofile <script.do>` — batch mode avoids GUI overhead; use with structured dofiles
  for repeatable flows.

## PDK / Tool Quirks

- **OpenROAD DFT**: `openroad -dft` scan insertion is functional for simple designs but does not
  support hierarchical scan chain stitching across IP boundaries — use Yosys DFT plugin or
  proprietary tools for SoC-level scan.
- **Yosys `synth -flatten` interaction**: Flattening before scan insertion eliminates hierarchy
  boundaries that block chain stitching, but significantly increases runtime on large designs.
  Flatten selectively at the scan boundary level.

## Notes

- JTAG boundary scan connectivity (`jtag_setup`) should be validated with a BSDL file checker
  before silicon — BSDL syntax errors cause test equipment to reject the device at incoming
  inspection.
