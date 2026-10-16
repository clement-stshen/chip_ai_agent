---
name: infrastructure
description: Detect licensed Synopsys, Cadence, and Siemens EDA tools and non-EDA host utilities. Never install EDA tools or configure fallback open-source EDA tools.
---

This skill is read by the infrastructure orchestrator. Do not spawn another
orchestrator when called mid-flow; return the requested detection or setup guidance.

## Purpose

Detect the host environment for the supported EDA vendors before a design flow
starts. Vendor tools are detect-only: never install, download, license, or
configure an EDA tool on the user's behalf. Never recommend an open-source EDA
tool or an EDA tool from another vendor as a substitute.

## Supported EDA Vendors

- Synopsys: VCS, Verdi, SpyGlass, Design Compiler, PrimeTime, VC Formal,
  DFTMAX/TetraMAX, StarRC, Synplify, Platform Architect, Fusion Compiler.
- Cadence: Xcelium, Genus, Innovus, Tempus, JasperGold, Conformal, Voltus,
  Modus, Stratus, Liberate, Virtual System Platform.
- Siemens: Questa, Calibre, Tessent, Catapult, Veloce, Aprisa.

The executable inventory in `infra_detect.py` is authoritative. Do not extend it
with non-vendor EDA tools. Non-EDA utilities such as Python, Bash, Make, GCC,
LLVM, GDB, OpenOCD, and QEMU may be detected as host infrastructure; they are not
EDA substitutes and must not be described as part of the supported EDA inventory.

## Detection Rules

1. Run `chip_infra_detect`; do not independently scan, install, or download EDA
   software.
2. Report available products grouped under exactly `synopsys`, `cadence`, and
   `siemens`, along with the executable path returned by detection.
3. Report missing vendor tools as unavailable. Suggest that the user load the
   site's licensed environment module or contact their EDA administrator; do
   not suggest package managers, source builds, containers, or alternate tools.
4. Report host utilities separately from EDA products.
5. Do not create wrapper scripts, MCP configuration snippets, tool manifests,
   installation scripts, or automatic module-load scripts.
6. Do not claim a tool ran, passed, or is licensed based only on its presence in
   `PATH`. Tool execution and license availability must be verified by the
   domain flow that needs the tool.

## Output

Return a concise report containing:

- Vendor product availability and executable paths.
- Missing products required by the requested flow.
- Available and missing non-EDA host utilities, in a separate section.
- A clear limitation when no supported vendor tool is available. Stop before
  execution and request a user-provided licensed environment; do not fall back.

## Sign-Off

Infrastructure detection passes when the inventory is reported accurately and
each requested EDA stage has an available tool from one of the three supported
vendors. Detection alone is not design-flow sign-off and does not prove a license
checkout or successful tool execution.