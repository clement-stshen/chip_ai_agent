# Formal Verification Domain Knowledge

## Known Failure Patterns

- **Vacuous proofs from over-constrained environment**: A vacuous proof means the `assume`
  constraints in `environment_setup` make the input space unreachable. Run vacuity check
  (`sby --vacuity`) after every environment iteration. If vacuity is detected, relax constraints
  one at a time — do not remove all constraints and re-add, as this loses context.
- **Insufficient bound depth**: SymbiYosys `--depth` must be set to at least `pipeline_depth + 2`
  to exercise all pipeline stages. Shallow bounds produce false "PASS" results for properties that
  only fire at the end of a pipeline.
- **LEC failures after synthesis**: LEC unmatched points after synthesis almost always indicate
  clock-gating cells that need equivalence mapping (`set_dont_touch` or explicit mapping script).
  Provide the synthesis tool's clock-gating cell list to the LEC tool before running.

## Successful Tool Flags

- `sby -f <task>.sby --depth <N>` — always set `--depth` explicitly; never rely on default bound.
- `sby --multiclock` — required when the design has multiple clock domains; single-clock mode
  silently ignores cross-domain paths.
- `jg -allow_empty_cex` — prevents JasperGold from treating an empty CEX set as proof of vacuity;
  use with explicit vacuity check script.

## PDK / Tool Quirks

- **Z3 vs Boolector for bitvector arithmetic**: Z3 is generally faster for designs with heavy
  arithmetic; Boolector outperforms Z3 on pure Boolean problems. Try both when a proof runs
  for > 30 minutes without result.
- **Yosys `prep` before sby**: Running `yosys -p "prep -top <top>"` on the design before
  invoking SymbiYosys catches synthesis elaboration errors early and significantly reduces
  proof setup time.

## Notes

- CEX found for a P0 property = hard blocker. Suspend the formal flow, report to the RTL
  team with the full counterexample trace, and do not retry until RTL fix is confirmed.
