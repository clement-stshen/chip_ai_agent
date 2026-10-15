#!/usr/bin/env python3
"""Standalone UVM IEEE 1800.2-2020 static compliance checker.

Bundled inside the check_uvm_compliance skill so any agent can directly
reuse it right after generating a testbench:

    python3 check_uvm_compliance.py <project_root>

<project_root> must contain rtl/ and tb/ (or the .sv files directly).
Exit 0 + "ALL CHECKS PASSED" = compliant; exit 1 lists every violation.
No simulator, no UVM library, no network required.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PAIRS = [("class", "endclass"), ("module", "endmodule"),
         ("package", "endpackage"), ("interface", "endinterface"),
         ("function", "endfunction"), ("task", "endtask"),
         ("clocking", "endclocking"), ("covergroup", "endgroup")]


def strip_comments(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def strip_strings(t: str) -> str:
    """Remove double-quoted string literals (word counting only)."""
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', t)


def collect_sv(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for p in sorted(root.rglob("*.sv")) + sorted(root.rglob("*.svh")):
        try:
            files[str(p.relative_to(root))] = strip_comments(p.read_text(errors="ignore"))
        except OSError:
            continue
    return files


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not root.exists():
        print(f"ERROR: project root not found: {root}")
        return 1
    sv = collect_sv(root)
    if not sv:
        print(f"ERROR: no SystemVerilog files under {root}")
        return 1

    fails: list[str] = []

    # R1: structural keyword pairing
    for name, t in sv.items():
        code = strip_strings(t)
        for a, b in PAIRS:
            if a == "clocking":
                # count declarations only; modport refs like
                # "modport drv (clocking drv_cb, ...)" are not new blocks
                na = len(re.findall(r"^\s*clocking\s+\w+", t, re.M))
                nb = len(re.findall(r"\bendclocking\b", t))
            elif a in ("function", "task"):
                # extern decls are not block openings; "with function sample()"
                # inside covergroups is not a function body either
                na = (len(re.findall(rf"\b{a}\b", code))
                      - len(re.findall(rf"extern\s+{a}\b", code))
                      - len(re.findall(rf"with\s+{a}\b", code)))
                nb = len(re.findall(rf"\b{b}\b", code))
            else:
                na, nb = len(re.findall(rf"\b{a}\b", code)), len(re.findall(rf"\b{b}\b", code))
            if na != nb:
                fails.append(f"R1 {name}: {a}={na} but {b}={nb}")

    joined = "\n".join(sv.values())

    # R2: every uvm class factory-registered
    for name, t in sv.items():
        for m in re.finditer(r"class\s+(\w+)\s+extends\s+(uvm_\w+)", t):
            cls = m.group(1)
            block = t[m.start():]
            reg = re.search(r"`uvm_(component|object)_utils", block[:block.find("endclass") if "endclass" in block else len(block)])
            if not reg:
                fails.append(f"R2 {name}: class {cls} extends {m.group(2)} but not factory-registered")

    # R3-R8: component conventions (each only if the component exists)
    def has(pat): return re.search(pat, joined) is not None

    if has(r"class\s+\w+\s+extends\s+uvm_driver") :
        if not has(r"seq_item_port\.get_next_item") or not has(r"seq_item_port\.item_done"):
            fails.append("R4 driver: missing seq_item_port.get_next_item/item_done")
        if not has(r"uvm_config_db"):
            fails.append("R3 driver: vif not obtained via uvm_config_db")
    if has(r"class\s+\w+\s+extends\s+uvm_monitor") and not has(r"uvm_analysis_port"):
        fails.append("R5 monitor: no uvm_analysis_port")
    if has(r"class\s+\w+\s+extends\s+uvm_scoreboard") and not has(r"uvm_analysis_imp"):
        fails.append("R6 scoreboard: no uvm_analysis_imp")
    if has(r"class\s+\w+\s+extends\s+uvm_agent") and not (
        has(r"get_is_active\(\)")
        # legacy-but-valid config-object style: agent reads a config holding
        # uvm_active_passive_enum and compares against UVM_ACTIVE
        or (has(r"uvm_active_passive_enum") and has(r"UVM_ACTIVE"))
    ):
        fails.append("R7 agent: active/passive via neither get_is_active() nor config object")
    if has(r"class\s+\w+\s+extends\s+uvm_sequence") and not (has(r"start_item") and has(r"finish_item")):
        fails.append("R8 sequence: missing start_item/finish_item body")

    # R9: interface clocking + modport
    ift = [t for n, t in sv.items() if re.search(r"^\s*interface\b", t, re.M)]
    if ift and not all(("clocking" in t and "modport" in t) for t in ift):
        fails.append("R9 interface: missing clocking block or modport")

    # R10: test objection lifecycle
    tests = [t for n, t in sv.items() if re.search(r"extends\s+uvm_test", t)]
    # base test classes without run_phase delegate objections to derived tests
    run_tests = [t for t in tests if "run_phase" in t]
    if run_tests and not all(("raise_objection" in t and "drop_objection" in t) for t in run_tests):
        fails.append("R10 test: objection raise/drop unbalanced")

    # R11: tb_top config_db + run_test
    tops = [t for n, t in sv.items() if re.search(r"^\s*module\s+tb_\w+", t, re.M)]
    if tops and not all(("uvm_config_db" in t and "run_test(" in t) for t in tops):
        fails.append("R11 tb_top: missing uvm_config_db set / run_test()")

    # R12: coverage separated from scoreboard (uvm_subscriber present when both exist)
    if has(r"extends\s+uvm_scoreboard") and has(r"covergroup") and not has(r"extends\s+uvm_subscriber"):
        fails.append("R12 coverage: covergroup not in a separate uvm_subscriber")

    # R13: direct DUT signal access outside clocking block in classes (heuristic)
    for name, t in sv.items():
        for m in re.finditer(r"vif\.(?!drv_cb|mon_cb)\w+\s*<=", t):
            fails.append(f"R13 {name}: drives vif signal outside clocking block: {m.group(0)}")
            break

    if fails:
        print(f"UVM IEEE 1800.2-2020 compliance check FAILED ({len(fails)} violation(s)):")
        for f in fails:
            print(" -", f)
        return 1
    print("UVM IEEE 1800.2-2020 static compliance: ALL CHECKS PASSED")
    print(f"  files checked: {len(sv)} under {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
