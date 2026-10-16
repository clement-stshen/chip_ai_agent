# STA Domain Knowledge

## Known Failure Patterns

- **Propagated clocks required for hold analysis**: Confirm the selected vendor STA flow uses
  propagated clocks before hold checks; ideal-clock analysis can report false-clean hold results.
- **Multi-corner hold closure needs target library hold_margin**: Multi-corner hold closure in
  sky130 usually requires setting a `hold_margin` in the target liberty file. The default
  hold_margin of 0 ps is insufficient for signoff at slow-slow corner with RCMAX parasitics —
  add 50–100 ps margin.
- **ECO cells > 2% → upstream issue**: If ECO cell count exceeds 2% of total cells during
  `eco_guidance`, this almost always indicates a floorplan or CTS issue upstream — not a timing
  exception problem. Escalate to the physical design team rather than continuing ECO iteration.
- **Parasitic extraction accuracy for hold**: Extraction accuracy significantly affects hold
  timing at advanced nodes. Use SPEF from a qualified extraction flow (Calibre xRC or StarRC)
  with calibrated rules.

## Successful Tool Flags

- `report_timing -path_type full_clock_expanded -delay_type max -nworst 10` — `full_clock_expanded`
  shows full clock network paths; essential for diagnosing clock skew contributions to WNS.
- `report_slack_histogram -num_bins 20` — quick overview of slack distribution; use before
  detailed path analysis to understand whether violations are widespread or concentrated.

## PDK / Tool Quirks

- **PrimeTime POCV vs AOCV**: PrimeTime POCV (parametric OCV) is more accurate than AOCV for
  advanced nodes but requires POCV coefficient files from the PDK vendor. Using AOCV on a design
  that has POCV coefficients available leaves pessimism on the table.
- **Tempus multi-mode multi-corner**: Tempus MMMC setup requires a `constraint_mode` and
  `delay_corner` for every combination — missing combinations produce incorrect "all clear" reports
  for unconstrained paths.

## Notes

- STA signoff requires `setup_wns_ns >= 0` AND `setup_tns_ps == 0` AND `hold_wns_ps >= 0`
  AND `hold_tns_ps == 0` at ALL corners. A single failing corner blocks tape-out.
