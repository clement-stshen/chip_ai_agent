# Formal Verification Domain Knowledge

## Known Failure Patterns

- **Vacuous proofs from over-constrained environment**: A vacuous proof means the `assume`
  constraints in `environment_setup` make the input space unreachable. Run the selected vendor
  tool's vacuity check after every environment iteration. If vacuity is detected, relax constraints
  one at a time — do not remove all constraints and re-add, as this loses context.
- **Insufficient bound depth**: Bounded proofs must cover at least `pipeline_depth + 2`
  cycles to exercise all pipeline stages. Shallow bounds produce false "PASS" results for
  properties that only fire at the end of a pipeline.
- **LEC failures after synthesis**: LEC unmatched points after synthesis almost always indicate
  clock-gating cells that need equivalence mapping (`set_dont_touch` or explicit mapping script).
  Provide the synthesis tool's clock-gating cell list to the LEC tool before running.

## PDK / Tool Quirks

## Notes

- CEX found for a P0 property = hard blocker. Suspend the formal flow, report to the RTL
  team with the full counterexample trace, and do not retry until RTL fix is confirmed.
