# Firmware Domain Knowledge

## Known Failure Patterns

- **QEMU peripheral emulation gaps**: QEMU peripheral emulation gaps cause false failures in
  `bsp_development`. If a BSP test fails on QEMU but the register map looks correct, check whether
  the peripheral is actually emulated — run `qemu-system-arm -machine help` and cross-reference
  peripheral list. Use RTL simulation or FPGA bring-up to validate unimplemented peripherals.
- **FreeRTOS stack overflow silent corruption**: Stack overflows without `configCHECK_FOR_STACK_OVERFLOW=2`
  corrupt adjacent task stacks silently, producing non-deterministic crashes. Always build FreeRTOS
  with `configCHECK_FOR_STACK_OVERFLOW=2` and `configUSE_MALLOC_FAILED_HOOK=1` during development.
- **Bare-metal clock tree validation**: Peripheral init before clock tree validation causes
  intermittent failures that are extremely difficult to root-cause. Always validate PLL lock and
  clock dividers before initialising any peripheral in `bsp_development`.

## Successful Tool Flags

- `arm-none-eabi-gcc -fstack-usage` — generates `.su` files with per-function stack usage;
  use to calculate worst-case stack depth before setting FreeRTOS task stack sizes.
- `openocd -f interface/<probe>.cfg -f target/<mcu>.cfg -c "program <elf> verify reset exit"` —
  combined flash-program-and-verify command; the `verify` step catches flash write failures
  that corrupt the image silently.
- `riscv64-unknown-elf-objdump -d --visualize-jumps` — useful for spotting unexpected branches
  in startup code during bring-up.

## PDK / Tool Quirks

- **J-Link RTT buffer sizing**: Increase `SEGGER_RTT_BUFFER_SIZE_UP` to at least 4096 for bring-up
  logging; the default 1024 bytes causes log drops at high baud rates.
- **TRACE32 JTAG speed**: Lower JTAG clock to ≤ 1 MHz during early bring-up until power delivery
  is validated; marginal power rails cause JTAG corruption at higher speeds.

## Notes

- `stress_test_24h_clean` is the sign-off gate — run it on target hardware, not QEMU.
  A QEMU 24h pass does not substitute for hardware validation.
