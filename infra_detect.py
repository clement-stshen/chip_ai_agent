"""Infrastructure detection: Synopsys / Cadence / Siemens EDA only.

EDA detection is restricted to Synopsys, Cadence, and Siemens. Non-EDA utilities
(python/gcc/llvm/debug probes) remain detectable as host infrastructure. Vendor
tools are detect-only — the agent never installs or licenses them.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# Non-EDA utilities only. Anything that designs/verifies/implements silicon
# must come from the three EDA vendors below.
UTILITIES = [
    "python3", "bash", "make", "gcc", "clang", "llvm-config", "uv",
    "gdb", "openocd", "qemu",
]

# (vendor, product, candidate binaries) — binaries are what `which` sees.
VENDOR_TOOLS: list[tuple[str, str, list[str]]] = [
    ("synopsys", "vcs", ["vcs"]),
    ("synopsys", "verdi", ["verdi"]),
    ("synopsys", "spyglass", ["spyglass"]),
    ("synopsys", "design-compiler", ["dc_shell", "dc_shell-t"]),
    ("synopsys", "prime-time", ["pt_shell", "pt_shell64"]),
    ("synopsys", "vc-formal", ["vcf", "vcf_sh"]),
    ("synopsys", "dftmax", ["tmax"]),
    ("synopsys", "starrc", ["starrc"]),
    ("synopsys", "synplify", ["synplify"]),
    ("cadence", "xcelium", ["xrun", "xmsim"]),
    ("cadence", "genus", ["genus"]),
    ("cadence", "innovus", ["innovus"]),
    ("cadence", "tempus", ["tempus"]),
    ("cadence", "jaspergold", ["jg"]),
    ("cadence", "conformal", ["conformal", "lec"]),
    ("cadence", "voltus", ["voltus"]),
    ("cadence", "stratus", ["stratus"]),
    ("siemens", "questa", ["vsim", "questa", "qrun"]),
    ("siemens", "calibre", ["calibre"]),
    ("siemens", "tessent", ["tessent"]),
    ("siemens", "catapult", ["catapult"]),
    ("siemens", "veloce", ["veloce"]),
]

VENDORS = ("synopsys", "cadence", "siemens")


def detect_tools() -> dict:
    utilities = {}
    for t in UTILITIES:
        path = shutil.which(t)
        utilities[t] = {"available": path is not None, "path": path}

    vendor: dict[str, dict] = {v: {} for v in VENDORS}
    for v, product, binaries in VENDOR_TOOLS:
        hit = next((b for b in binaries if shutil.which(b)), None)
        vendor[v][product] = {
            "available": hit is not None, "binary": hit,
            "policy": "detect-only (never auto-install/license)",
            "setup": None if hit else
                     f"module load {v} toolkit providing {binaries[0]}",
        }

    per_vendor_avail = {v: sum(1 for p in vendor[v].values()
                               if p["available"]) for v in VENDORS}
    return {
        "utilities": {k: x for k, x in utilities.items() if x["available"]},
        "utilities_missing": [k for k, x in utilities.items()
                              if not x["available"]],
        "vendors": vendor,
        "vendors_available": per_vendor_avail,
        "open_source_eda_policy":
            "removed by directive — Synopsys/Cadence/Siemens only",
        "summary": (
            f"utilities={sum(x['available'] for x in utilities.values())}"
            f"/{len(utilities)} "
            + " ".join(f"{v}={per_vendor_avail[v]}/{len(vendor[v])}"
                       for v in VENDORS)),
    }
