# Memory IP Design Domain Knowledge

## Known Failure Patterns

- **Pin-name drift between `.lib`, `.lef`, and `.v`**: Compiler-generated views can disagree on
  pin naming (e.g. `CLK` vs `clk`, `WEN` vs `WEB`) when the wrapper is hand-edited after
  generation. Nothing errors at generation time — the mismatch surfaces as an unconnected port
  at PD or an LEC mismatch much later. Always diff the pin lists across all three views before
  declaring `view_generation` clean.
- **Typical-corner macro selection**: Selecting a macro on typical-corner access time leaves no
  margin at the slow corner, where the sense-amp path degrades disproportionately compared to
  logic. A macro that passes at typical and fails at SS is the most common cause of a late
  loop-back from STA. Always select on slow-corner margin.
- **Permissive behavioural model hides collision bugs**: If the `.v` behavioural model returns
  old data on a write-during-read collision while the real macro returns X, the testbench passes
  and silicon fails. The behavioural model must propagate X for exactly the collision cases the
  macro does not define.
- **ECC treated as a substitute for redundancy**: ECC corrects soft errors; redundancy replaces
  hard defects found at test. Counting ECC toward the post-repair yield target overstates yield
  and is discovered only at wafer sort. Keep the two calculations separate.

## Vendor Tool Notes

- Verify that the selected licensed compiler supports the required depth, width, port arrangement,
  and PVT corners before treating a macro as a candidate.
- Use vendor qualification reports for pre-hardened macros and record any fixed-size area
  over-provisioning at `macro_selection`.

## Notes

- Record the rejection rationale for every losing macro candidate. Re-spins revisit the same
  trade space, and the reason a candidate lost (aspect ratio, slow-corner margin, leakage) is the
  highest-value thing to carry forward.
- Repair-register width is a hard handoff number to DFT's `bist_insertion`. Changing the spare
  row/column count after DFT has built the BISR chain forces a DFT loop-back — freeze it at
  `redundancy_repair`.
