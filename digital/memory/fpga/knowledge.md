# FPGA Domain Knowledge

## Known Failure Patterns

- **Memory inference mismatch**: Match RTL read latency, reset behavior, width, and port count to
  the selected device's supported memory primitives; verify inferred resources in vendor reports.
- **Arithmetic resource inference**: Keep multiply-accumulate structures explicit and inspect
  synthesis reports to confirm mapping to the intended device resources.
- **Prototype frequency target**: Set the FPGA prototype frequency target to 1/3 of the ASIC
  target to account for FPGA fabric overhead. For example, a 1 GHz ASIC target maps to ~333 MHz
  FPGA prototype target. Document the scale factor explicitly in the sign-off report.

## PDK / Tool Quirks

## Notes

- All performance measurements on the FPGA prototype must be recorded at prototype frequency
  with the ASIC scale factor noted. Reporting FPGA MHz directly as a performance number
  without the scale factor is misleading.
