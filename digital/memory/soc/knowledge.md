# SoC Integration Domain Knowledge

## Known Failure Patterns

- **AXI4 memory map conflicts → chip_level_sim failure**: AXI4 memory map conflicts are a common
  cause of `chip_level_sim` failures. Before `top_integration`, generate a full memory map from
  all IP block configurations and verify no address ranges overlap.
- **IP version drift**: Unpinned IP revisions can change interfaces unexpectedly. Record exact
  IP revisions and validate interface compatibility before integration.
- **Bus fabric address decoder verification**: Address decoder errors in `bus_fabric_setup` are
  not caught by RTL lint. Validate the decoder with a directed simulation test that walks all
  address boundaries (base, base+1, top-1, top) before `top_integration`.

## PDK / Tool Quirks

## Notes

- `unqualified_ips: 0` is a hard sign-off gate. Never proceed to synthesis with unqualified IP —
  IP qualification failures discovered post-synthesis require full re-integration.
