---
name: check_handshake_stability
description: |
  Tier-1 deterministic VALID/READY handshake-stability check for AXI / AXI4 / ACE / CHI / AHB / APB / UCIe / generic VALID-READY interfaces. Verifies that VALID stays asserted (and the payload is held stable) until READY rises -- i.e. the producer never drops the handshake mid-flight. Channels and the (VALID, READY) signal pair for each channel are derived from the YAML protocol spec, so no per-protocol code is needed. This is a pure deterministic signal walk: no LLM judgment is involved in the check itself, no transactions need to be reconstructed, and the response is authoritative. Use when the user explicitly asks to verify handshake stability, "did VALID drop before READY", VALID/READY protocol compliance, or whether the handshake was well-formed on a specific interface scope. DO NOT use for broad spec-rule audits ("check all compliance rules"), burst-boundary checks, ordering checks, or snoop checks -- those go through the LLM-as-judge compliance path via `protocol_analyze_query`.
target: [protocol]
examples:
  - "Check handshake stability on /test_top/dut/axi_if[0]"
  - "Did VALID drop before READY on /tb/dut/master_0?"
  - "Verify VALID/READY protocol compliance for the AXI write channel on /top/dut/axi_if"
  - "Was the handshake well-formed between 0ns and 1us on /test_top/ds_phy_if/phy_if[0]?"
  - "Check handshake stability on the AXI read channel"
  - "Validate handshake on CHI interface /tb/chi_if[1]"
---

## Steps

1. Resolve the interface scope from the user prompt.
   - If the user gave a fully-qualified scope path, use it as-is.
   - If only a partial or short name was given, call `protocol_find_signals` with a narrow pattern (e.g. `*<scope_hint>*valid*`) to locate a candidate scope. Confirm the path before proceeding.
   - If the user mentioned a protocol family (AXI, CHI, UCIe, ...) but no scope at all, call `protocol_discover_interfaces` first and pick the matching one. If multiple candidates are returned, ask the user to disambiguate before calling the check.

2. Determine the protocol mnemonic.
   - Prefer an explicit one from the prompt (`AXI`, `AXI4`, `ACE`, `CHI`, `AHB`, `APB`, `UCIe`, ...).
   - If none was given, omit the `protocol` argument; the tool will fall back to the analyzer's last-detected protocol. If the tool replies with a "protocol is unknown" hint, run `protocol_discover_interfaces` once and retry.

3. Determine the analysis window.
   - If the user gave explicit start/end times (e.g. "between 100ns and 1us"), pass them through as `start_time` / `end_time` strings using the user's stated unit. Do NOT convert units yourself -- the tool handles ps / ns / us / ms / fs / as suffixes and bare integers (treated as FSDB-native ticks).
   - If no window was given, omit both arguments. The tool defaults to the full simulation window auto-detected from the FSDB.

4. Call `protocol_check_handshake(scope=<resolved_scope>, start_time=<...>, end_time=<...>, protocol=<...>)` exactly once. This is a deterministic signal walk; do NOT call it multiple times with different parameters hoping for a different answer.

5. Render the response verbatim.
   - If the tool reports "Handshake stability holds ...", say so. Do NOT speculate that there might still be a problem -- the check is authoritative for the requested window and channels.
   - If the tool reports violations, list each channel's count and the first few timestamps the tool included. Group by channel. Do NOT add an LLM "explanation" claiming the violation might be a false positive -- this is a deterministic finding.
   - If the tool returns a setup error ("scope not found", "protocol unknown", "no spec registered"), follow the tool's hint exactly (e.g. run `protocol_discover_interfaces`, ask user to clarify scope) and retry the same call once. Do not loop more than twice.

6. Stop after step 5. Do NOT chain a follow-up `protocol_analyze_query` or any LLM-as-judge compliance call -- the user explicitly asked for handshake stability and the deterministic answer is final.
