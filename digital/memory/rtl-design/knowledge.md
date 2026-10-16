# RTL Design Domain Knowledge

## Known Failure Patterns

- **Lint warnings are not equivalent across tools**: Review the selected vendor linter's rules and
  waivers; a clean result from one checker does not prove coverage of another tool's rules.
- **CDC violations from multi-bit signals**: Multi-bit signals crossing clock domains require both
  a synchronizer AND Gray encoding. A 2-FF synchronizer alone is insufficient for multi-bit vectors;
  the intermediate states cause functional errors that are intermittent and hard to reproduce in
  simulation.
- **Async reset flops need reset-removal SDC constraints**: Asynchronous reset flops require
  explicit reset-removal timing constraints in the SDC (`set_max_delay -datapath_only` from reset
  deassertion to first flop clock edge). Without these, STA will either flag false violations or
  miss real metastability windows.

## PDK / Tool Quirks

- **SpyGlass CDC vs JasperGold CDC**: SpyGlass CDC reports more false positives on Gray-encoded
  buses; JasperGold CDC gives fewer false positives but misses some structural CDC patterns.
  Use SpyGlass first to get full coverage, then waive false positives with documented rationale.

## Notes

- RTL sign-off package must include `filelist.f` with relative paths. Absolute paths in filelist
  break downstream synthesis flows that run from a different working directory.
