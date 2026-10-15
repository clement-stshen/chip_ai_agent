# Verification Domain Knowledge

## Known Failure Patterns

- **UVM factory override failures → uvm_tb_build failures**: UVM factory override issues are the
  #1 cause of `uvm_tb_build` failures. Symptoms: `uvm_fatal` with "object of type X expected but
  Y received" at simulation start. Root cause: override registered after `run_test()` call, or
  type name string mismatch (case-sensitive). Always register overrides in `build_phase`, before
  `super.build_phase()`.
- **Functional coverage closure stalls at constrained_random**: Stalls in functional coverage
  closure are often caused by unreachable corner cases that random stimulus cannot hit. Before
  adding more constrained random sequences, analyze the uncovered bins — if they require specific
  ordering of >3 events, write a directed test targeting exactly that sequence.
- **Assertion-based coverage complement**: Assertion-based coverage (via `$rose`, `$fell`, SVA
  covers) complements functional coverage by catching protocol violations that would otherwise
  only appear as silent data corruption. Wire SVA cover points to the coverage database to avoid
  double-counting them as functional coverage.

## Successful Tool Flags

- `verilator --coverage --coverage-line --coverage-toggle -Wno-UNOPTFLAT` — enables line,
  toggle, and user coverage collection; `-Wno-UNOPTFLAT` suppresses expected warnings from
  UVM dynamic connections.
- `vcs -sverilog +vcs+lic+wait +UVM_NO_RELNOTES -cm line+cond+fsm+tgl` — `+vcs+lic+wait`
  prevents licence timeout failures in batch regressions; `-cm` flags enable all coverage types.
- `xrun -uvm -coverage all -covworkdir <dir>` — Xcelium coverage merge from multiple regression
  runs; `-covworkdir` must be consistent across all runs for merge to succeed.

## PDK / Tool Quirks

- **Verilator UVM library**: The open-source UVM library (`uvm-core`) compiles with Verilator
  but does not support all UVM phasing features. Specifically, `uvm_objection` timeout-based
  drain time is not supported — use explicit event-based drain instead.
- **cocotb + Verilator coverage**: cocotb does not natively export Verilator coverage to the
  standard UCDB format. Use `verilator_coverage --write-info <info> <dat>` to convert, then
  `urg -dir <info>` for HTML reports.

## Notes

- `open_p0_bugs: 0` is a hard sign-off gate. Do not proceed to `regression_signoff` with any
  P0 or P1 bugs open — re-opening a regression signoff after a deferred P0 fix costs a full
  regression re-run.
