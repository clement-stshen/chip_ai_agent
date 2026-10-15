# SoC Integration Domain Knowledge

## Known Failure Patterns

- **AXI4 memory map conflicts → chip_level_sim failure**: AXI4 memory map conflicts are the #1
  cause of `chip_level_sim` failures. Before `top_integration`, generate a full memory map from
  all IP block configurations and verify no address ranges overlap. FuseSoC address map exports
  can be validated with `fusesoc gen --target sim <core>` before integration.
- **FuseSoC IP version pinning**: FuseSoC core dependency resolution fails silently when IP
  versions are unpinned and the registry has newer incompatible versions. Always pin IP versions
  in `<design>.core` using `=` (exact) version constraints, not `^` (compatible) — compatible
  constraints have caused breakage when upstream IPs changed interfaces.
- **Bus fabric address decoder verification**: Address decoder errors in `bus_fabric_setup` are
  not caught by RTL lint. Validate the decoder with a directed simulation test that walks all
  address boundaries (base, base+1, top-1, top) before `top_integration`.

## Successful Tool Flags

- `fusesoc --cores-root <path> run --target sim <core>` — `--cores-root` overrides the default
  registry; use to point at local IP copies during integration before publishing to registry.
- `verilator --sc --exe --build -Wno-UNOPTFLAT <files>` — `--sc` enables SystemC output needed
  for cocotb/TLM integration; `-Wno-UNOPTFLAT` suppresses expected warnings from AXI bus
  combinational loops.
- `edalize build --tool <tool>` — Edalize abstracts tool-specific project file generation;
  prefer over hand-written Makefiles for simulator portability.

## PDK / Tool Quirks

- **Verilator AXI4 burst simulation**: Verilator does not model AXI4 burst interleaving by
  default — cocotb or a VIP is required for protocol-level bus verification. Verilator alone
  is sufficient only for functional correctness, not protocol compliance.
- **FuseSoC .core file VLNV**: VLNV (Vendor:Library:Name:Version) must be unique across all
  cores in the registry. Duplicate VLNVs cause FuseSoC to silently use the first match found,
  which may be the wrong version.

## Notes

- `unqualified_ips: 0` is a hard sign-off gate. Never proceed to synthesis with unqualified IP —
  IP qualification failures discovered post-synthesis require full re-integration.
