# Physical Design Domain Knowledge

## Known Failure Patterns

- **Placement density and congestion**: High target utilization can create routing
  congestion. Set margins from the selected vendor's congestion reports and target-process
  rules; do not treat generic density thresholds as sign-off criteria.
- **Post-route timing closure ECO rounds**: If WNS has not converged after three ECO rounds,
  escalate to floorplan or placement review. Incremental ECO will not close timing when the
  root cause is congestion or clock-tree structure.
- **LVS failures from missing substrate tie-offs**: Check that the target PDK library includes
  tie-off cells and that the implementation flow inserts them at the required pitch.
- **Global-route status is not detailed-route sign-off**: Require the selected vendor's detailed
  routing and sign-off DRC reports; global congestion metrics alone are insufficient.

## Notes

- Core utilization above the agreed design limit is a hard stop. Set that limit from the target
  process, package, and licensed implementation flow rather than a generic threshold.
- Preserve native timing, DRC/LVS, antenna, IR/EM, and congestion reports for every sign-off run.