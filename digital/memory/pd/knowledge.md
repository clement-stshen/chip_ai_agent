# Physical Design Domain Knowledge

## Known Failure Patterns

- **ORFS density > 65% → routing congestion**: OpenROAD/ORFS placement density above 65% almost
  always correlates with routing congestion (DRC violations in routing stage). Reduce target
  density in `floorplan` to 60–65% before retrying; do not push past 70% without manual congestion
  analysis.
- **CTS target skew for sky130 at 500 MHz**: Use 50 ps target skew for 500 MHz designs in sky130.
  Tighter targets (< 30 ps) are unreachable with OpenROAD CTS and will cause the CTS stage to
  loop indefinitely.
- **Post-route timing closure ECO rounds**: Post-route timing closure typically requires 2–3 ECO
  rounds. If WNS has not converged after 3 rounds, escalate to floorplan revision — incremental
  ECO will not close timing if the root cause is placement congestion.
- **LVS failures from missing substrate tie-offs**: The most common LVS failure in sky130 is
  missing n-well tie-offs and substrate tie-offs for standard cells. Ensure the PDK standard
  cell library includes tie-off cells and that the floorplan inserts them at the required pitch.

## Successful Tool Flags

- `make DESIGN_CONFIG=... finish` (ORFS) — run the full pipeline to completion before reading
  `reports/.../metrics.json`; partial runs leave stale metrics files.
- `klayout -rd input=<gds> -r <drc_script.rb> -zz` — batch DRC mode; `-zz` suppresses GUI and
  is required for CI/CD integration.
- `openroad -no_init` with `read_lef`/`read_def`/`report_checks` TCL sequence — useful for
  one-shot timing queries on a routed design without reloading the full ORFS database.

## PDK / Tool Quirks

- **sky130 antenna rules**: sky130 antenna rules are stricter than most commercial PDKs. Enable
  antenna repair (`repair_antennas`) in OpenROAD after routing; expect 5–15% of nets to need
  repair on a typical design.
- **OpenROAD global routing vs detailed routing DRC**: Global routing DRC (overflow) does not
  guarantee detailed routing DRC clean. Always run `detailed_route` and check `drc_count` from
  the metrics file — not the global routing overflow count.

## Notes

- `core_area_util_pct` above 85% at sign-off is a hard stop — route congestion and ECO closure
  become intractable above this threshold in sky130 with OpenROAD.
