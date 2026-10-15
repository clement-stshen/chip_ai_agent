# Compiler Domain Knowledge

## Known Failure Patterns

- **LLVM backend register allocation errors**: Errors in `backend_dev` during register allocation
  almost always indicate the wrong calling convention is specified. Verify `CallingConv::ID` in
  `XXXCallingConv.td` matches the ABI spec before retrying codegen.
- **Custom extensions without MC layer**: RISC-V custom extensions require the `MC` (Machine Code)
  layer to be implemented before codegen can produce correct encodings. Attempting codegen without
  MC causes silent encoding errors that surface only in ATPG or silicon validation.
- **Miscompilation root cause**: Root cause is almost always instruction selection DAG patterns.
  Use `llc -debug-only=isel` to dump the SelectionDAG before and after legalization. Compare
  against the reference C output compiled with a known-good compiler (`riscv64-unknown-elf-gcc -O0`).

## Successful Tool Flags

- `clang -target riscv32-unknown-elf -march=rv32imXcustom` — use `-march` with custom extension
  string to exercise new instruction patterns end-to-end from Clang through LLC.
- `llc -verify-machineinstrs` — enables MachineInstr verification after each pass; catches
  malformed instructions that would otherwise silently produce wrong code.
- `llvm-mc --show-encoding` — verify binary encoding of each custom instruction before wiring
  into codegen; catches TableGen pattern mismatches early.

## PDK / Tool Quirks

- **QEMU peripheral emulation gaps**: QEMU may not emulate custom CSRs or non-standard MMIO
  peripherals. Runtime library tests that pass on QEMU but fail on silicon almost always involve
  an unimplemented QEMU peripheral — validate against RTL simulation or FPGA prototype.
- **GCC ABI for RISC-V custom extensions**: GCC requires a custom multilib configuration if the
  extension changes the calling convention. Without it, mixing `-march` flags between objects causes
  linker ABI conflicts.

## Notes

- Always run the full regression suite (`toolchain_validation`) with `-O0`, `-O1`, and `-O2`
  separately — many miscompilations only appear at optimization levels > 0.
