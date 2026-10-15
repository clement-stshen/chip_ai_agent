# HLS Domain Knowledge

## Known Failure Patterns

- **PIPELINE II=1 failure on memory-bound loops**: Vitis HLS `PIPELINE II=1` on memory-bound
  loops almost always fails because array accesses create resource conflicts. Resolve by partitioning
  arrays (`#pragma HLS ARRAY_PARTITION variable=<arr> cyclic factor=<N>`) or using `PIPELINE II=2`
  as an interim target while restructuring access patterns.
- **DATAFLOW pragma requires producer/consumer channels**: `#pragma HLS DATAFLOW` requires every
  producer-consumer pair to communicate via a stream or ping-pong buffer. Bypassing this (e.g.,
  using a regular array between DATAFLOW tasks) causes HLS to ignore the pragma silently with no
  error — verify with the dataflow viewer.
- **Latency target misses**: Latency target misses are almost always resolved by loop unrolling
  (`#pragma HLS UNROLL factor=<N>`) or partitioning arrays — not by increasing clock frequency.
  Try array partitioning first as it has lower area overhead than full unroll.

## Successful Tool Flags

- `vitis_hls -f <script.tcl>` with `config_compile -pipeline_loops 0` — disables automatic
  loop pipelining; use when manual `PIPELINE` directives are preferred over automatic insertion.
- `bambu --target-file=<xml> --top-fname=<func> --simulate` — always use `--simulate` to catch
  output mismatches at the HLS level before RTL QC.
- `circt-opt --lower-calyx-to-fsm` — useful for inspecting generated FSM structure from Calyx IR.

## PDK / Tool Quirks

- **Catapult reset inference**: Catapult infers resets from variable initialization in C++.
  Uninitialized variables that happen to read as zero in simulation may not have reset logic in
  RTL — explicitly initialize all variables used in reset-dependent logic.
- **Bambu vs Vitis for floating point**: Bambu generates IEEE-754 compliant FP units natively;
  Vitis HLS FP operations use Xilinx FP IP cores which are non-IEEE on NaN/infinity handling.
  Use Bambu for portability if FP edge cases matter.

## Notes

- Co-simulation output mismatch is always a blocker. Root cause before retry — do not assume
  the mismatch is a simulation artifact.
