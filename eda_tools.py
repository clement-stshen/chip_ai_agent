"""EDA tool bridge: VCS / Verdi / NPI discovery, invocation, degradation.

Environment model (matches this site):
  - Real EDA binaries may live on compute nodes, not the analysis host.
  - The authoritative source for tool homes is the environment modulefile
    (/usr/share/Modules/modulefiles/synopsys, /tools/Synopsys/scl/modulefile).
  - The NPI kit (/tools/Synopsys/temp/NPI) provides pynpi Python bindings;
    waveform DB access additionally requires a valid $VERDI_HOME.

Every tool call degrades gracefully: when a binary is missing the result
carries the exact setup command and a ready-to-run invocation string.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from .site_paths import (COMMON_ROOTS, MODULEFILES, NPI_ROOT,
                          TEMPLATE_TB, UVM_ROOT, UVM_TGZ_ROOT,
                          VERIF_AGENT_BIN, VERIF_AGENT_CONFIG)

TEMPLATE_ROOT = TEMPLATE_TB

# -- UVM reference library (Accellera, /tools/Synopsys/temp/uvm) -------------
# 6 releases ship unpacked next to their tarballs; the 1.x tarballs live in
# the parent dir, the 1800.2 ones inside uvm/. The project standard is the
# IEEE 1800.2-2020.3.1 kit. uvm-core-2020.3.1 is an identical twin (the
# "core" suffix is the Accellera GitHub repo name, not a feature subset).
# UVM_ROOT: see site_paths
UVM_TARBALLS: dict[str, Path] = {
    "uvm-1.0p1": UVM_TGZ_ROOT / "uvm-1.0p1.tar.gz",
    "uvm-1.1d": UVM_TGZ_ROOT / "uvm-1.1d.tar.gz",
    "uvm-1.2": UVM_TGZ_ROOT / "uvm-1.2.tar.gz",
    "1800.2-2020-2.0": UVM_ROOT / "UVM-18002-2020-20tar.gz",
    "1800.2-2020.3.1": UVM_ROOT / "UVM-1800.2-2020.3.1.tar.gz",
    "uvm-core-2020.3.1": UVM_ROOT / "uvm-core-2020.3.1.tar.gz",
}
DEFAULT_UVM_VERSION = "1800.2-2020.3.1"

# E4 (audit): AI/ML EDA enhancements from the site briefing deck
# (/mnt/hgfs/temp_tools/deepseek_markdown_20261012_9d20a4.md). The deck
# documents capabilities and control points but NOT command-line flags, so
# this table is deliberately flag-free: engineers pass site-verified options
# through run_simulation(extra_args=...). Never fabricate vendor switches.
EDA_ENHANCEMENTS: list[dict] = [
    {"feature": "vcs_dpo",
     "name": "VCS Dynamic Performance Optimization",
     "mechanism": "ML learns simulator settings from prior regressions; "
                  "compile+runtime, RTL/gate-level/low-power",
     "control": "learning-phase frequency is user-controlled",
     "version_dependency": "site VCS version — verify before enabling",
     "agent_use": "regression TAT reduction; measure via chip_qor_trends",
     "invocation": "site-verified options via run_simulation(extra_args)"},
    {"feature": "vcs_ico",
     "name": "VCS Intelligent Coverage Optimization",
     "mechanism": "RL-biased constrained-random stimulus; intra- and "
                  "inter-simulation learning",
     "control": "bias/seeding policy per project",
     "version_dependency": "site VCS version — verify before enabling",
     "agent_use": "coverage closure acceleration; holes tracked by "
                  "functional_coverage_pct gate",
     "invocation": "site-verified options via run_simulation(extra_args)"},
    {"feature": "verdi_rda",
     "name": "Verdi Regression Debug Automation",
     "mechanism": "Transaction Diff (reference+failure FSDB) / Message "
                  "Analysis (logs only) / Auto Binning (failure clustering)",
     "control": "which logs/waveforms/databases are wired in",
     "version_dependency": "site Verdi install ($VERDI_HOME)",
     "agent_use": "agent primitives map 1:1 — Message Analysis ≈ "
                  "chip_analyze_eda_log, Transaction Diff ≈ pynpi FSDB "
                  "compare, Auto Binning ≈ failure_class clustering; "
                  "root-cause confirmation stays with the engineer",
     "invocation": "chip_analyze_eda_log / chip_open_waveform / NPI tools"},
]


def _is_uvm_lib(path: Path) -> bool:
    return (path / "src" / "uvm_pkg.sv").exists()


def uvm_versions() -> dict[str, dict]:
    """Inventory the local Accellera reference library.

    For each version: {present, tarball, extracted} — `present` is true when
    either the unpacked kit or its tarball is on disk.
    """
    out: dict[str, dict] = {}
    for ver, tarball in UVM_TARBALLS.items():
        kit = UVM_ROOT / ver
        out[ver] = {
            "kit": str(kit), "extracted": _is_uvm_lib(kit),
            "tarball": str(tarball), "tarball_exists": tarball.exists(),
            "present": _is_uvm_lib(kit) or tarball.exists(),
        }
    return out


def resolve_uvm_home(project_root: str | Path,
                     version: str | None = None) -> str:
    """Resolve UVM_HOME: $UVM_HOME env wins, then a project-local extracted
    copy (uvm_lib/<version>), then the shared reference kit. Returns the
    project-local path as the caller-actionable default when nothing is
    extracted yet (run_vcs.sh auto-extracts from the tarball).
    """
    env = os.environ.get("UVM_HOME")
    if env:
        return env
    ver = version or os.environ.get("UVM_VERSION") or DEFAULT_UVM_VERSION
    proj = Path(project_root) / "uvm_lib" / ver
    if _is_uvm_lib(proj):
        return str(proj)
    shared = UVM_ROOT / ver
    if _is_uvm_lib(shared):
        return str(shared)
    return str(proj)


def _modulefile_homes() -> dict[str, str]:
    """Parse VERDI_HOME/VCS_HOME declarations from site modulefiles."""
    homes: dict[str, str] = {}
    for mf in MODULEFILES:
        p = Path(mf)
        if not p.exists():
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        for var in ("VERDI_HOME", "VCS_HOME"):
            m = re.search(rf'set\s+{var}\s+"([^"]+)"', text)
            if m:
                homes.setdefault(var, m.group(1))
    return homes


def _find_binary(name: str, extra_homes: dict[str, str]) -> tuple[str | None, str]:
    """Return (resolved_path_or_None, source)."""
    p = shutil.which(name)
    if p:
        return p, "PATH"
    home = extra_homes.get(f"{name.upper()}_HOME") or extra_homes.get(
        "VERDI_HOME" if name == "verdi" else "VCS_HOME")
    if name == "vcs" and home:
        for sub in ("bin/vcs", "linux64/bin/vcs"):
            c = Path(home) / sub
            if c.exists():
                return str(c), "modulefile"
    if name == "verdi" and home:
        c = Path(home) / "bin/verdi"
        if c.exists():
            return str(c), "modulefile"
    for root in COMMON_ROOTS:
        c = Path(root) / name / "Y-2026.03-SP1" / "bin" / name
        if c.exists():
            return str(c), "common-root"
    return None, ""


def discover() -> dict:
    homes = _modulefile_homes()
    tools = {}
    for name in ("vcs", "verdi"):
        path, src = _find_binary(name, homes)
        entry = {"available": path is not None, "path": path, "source": src}
        if path is None:
            declared = homes.get("VERDI_HOME" if name == "verdi" else "VCS_HOME", "")
            entry["declared_home"] = declared
            entry["home_exists"] = bool(declared) and Path(declared).exists()
            entry["setup"] = "module load synopsys   # then retry"
        tools[name] = entry
    # pynpi-backed waveform layer (npi_tools is the canonical owner of the
    # kit paths): importable now, activation gated on a REAL Verdi install
    # (npisys.init opens $VERDI_HOME/bin/npi — REA-verified gate).
    from .npi_tools import NPI_PY, NPI_ROOT as _NPI_KIT, npi_available
    npi = {
        "kit": str(_NPI_KIT),
        "kit_exists": _NPI_KIT.exists(),
        "pynpi_py": str(NPI_PY),
        "importable": (NPI_PY / "pynpi").exists(),
        "pynpi_importable": (NPI_PY / "pynpi" / "__init__.py").exists(),
        "ready": npi_available(),
        "requires": "real Verdi install ($VERDI_HOME/bin/npi) via "
                    "module load synopsys on EDA hosts",
        "waveform_requires": "valid $VERDI_HOME (binary install)",
        "demo_fsdb": str(next(_NPI_KIT.glob(
            "example/via_examples/NPI_Models/FSDB_Model/*/demo.fsdb"), "")),
    }
    versions = uvm_versions()
    uvm = {
        "root": str(UVM_ROOT),
        "versions": versions,
        "available": sorted(v for v, s in versions.items() if s["extracted"]),
        "tarballs": sorted(v for v, s in versions.items() if s["tarball_exists"]),
        "default_version": DEFAULT_UVM_VERSION,
        "default_home": resolve_uvm_home(TEMPLATE_ROOT),
    }
    # Synopsys verif-agent-mcp (4 VCS/URG/ipvgen tools): stdio adapter target
    va_venv = VERIF_AGENT_BIN
    va_cfg = VERIF_AGENT_CONFIG
    verif_agent = {
        "installed": va_venv.exists(),
        "config": str(va_cfg) if va_cfg.exists() else None,
        "stdio_command": (f"VERIF_AGENT_TRANSPORT=stdio VERIF_AGENT_BACKEND=stub "
                          f"{va_venv}") if va_venv.exists() else None,
    }
    return {"tools": tools, "modulefile_homes": homes, "npi": npi, "uvm": uvm,
            "enhancements": EDA_ENHANCEMENTS,
            "verif_agent_mcp": verif_agent,
            "summary": f"vcs={'OK' if tools['vcs']['available'] else 'missing'} "
                       f"verdi={'OK' if tools['verdi']['available'] else 'missing'} "
                       f"npi={'ready' if npi['ready'] else 'kit-only'} "
                       f"uvm_libs={len(uvm['available'])}"}


def build_vcs_command(project_root: str | Path,
                      testname: str | list[str] = "fifo_smoke_test",
                      extra_args: list[str] | None = None,
                      vcs_binary: str = "vcs") -> list[str]:
    """Build VCS compile argv; testname remains accepted for API compatibility.

    Simulation is launched separately by build_vcs_run_command().
    """
    root = Path(project_root).resolve()
    uvm_home = resolve_uvm_home(project_root)
    filelist = root / "sim/filelist.f"
    if isinstance(testname, list) and extra_args is None:
        extra_args = testname
    extra = [a for a in (extra_args or []) if a]
    return [
        vcs_binary, "-full64", "-sverilog", "-timescale=1ns/1ps", "-debug_access+all",
        f"+incdir+{uvm_home}/src", f"-f{filelist}", "-l", "comp.log", "-o", "simv",
        *extra,
    ]


def build_vcs_run_command(testname: str = "fifo_smoke_test") -> list[str]:
    """Build the generated simulator argv without interpreting user input."""
    return ["./simv", f"+UVM_TESTNAME={testname}",
            "+UVM_VERBOSITY=UVM_LOW", "-l", "sim.log"]


def run_simulation(project_root: str, testname: str = "fifo_smoke_test",
                   timeout: int = 600,
                   extra_args: list[str] | None = None) -> dict:
    """Compile + run a UVM simulation with VCS; parse the UVM report."""
    disc = discover()
    root = Path(project_root).resolve()
    sim_dir = root / "sim"
    vcs_binary = disc["tools"]["vcs"].get("path") or "vcs"
    compile_cmd = build_vcs_command(root, extra_args=extra_args,
                                    vcs_binary=vcs_binary)
    sim_cmd = build_vcs_run_command(testname)
    if not disc["tools"]["vcs"]["available"]:
        ready_command = (
            f"cd {shlex.quote(str(sim_dir))} && "
            f"{shlex.join(compile_cmd)} && {shlex.join(sim_cmd)}")
        return {
            "ok": False,
            "error": "VCS not available on this host",
            "setup": disc["tools"]["vcs"]["setup"],
            "declared_home": disc["tools"]["vcs"].get("declared_home"),
            "ready_command": ready_command,
            "note": "run on the EDA host / LSF compute node after module load",
        }

    simlog = sim_dir / "sim.log"
    complog = sim_dir / "comp.log"
    for log_path in (simlog, complog):
        try:
            log_path.unlink(missing_ok=True)
        except OSError as e:
            return {"ok": False, "error": f"cannot clear stale log {log_path}: {e}"}

    started = time.monotonic()
    try:
        compile_proc = subprocess.run(
            compile_cmd, cwd=sim_dir, capture_output=True, text=True,
            timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"VCS compilation timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": f"failed to launch: {e}"}

    sim_proc = None
    if compile_proc.returncode == 0:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            return {"ok": False, "compile_returncode": 0,
                    "error": f"simulation timed out after {timeout}s"}
        try:
            sim_proc = subprocess.run(
                sim_cmd, cwd=sim_dir, capture_output=True, text=True,
                timeout=remaining)
        except subprocess.TimeoutExpired:
            return {"ok": False, "compile_returncode": 0,
                    "error": f"simulation timed out after {timeout}s"}
        except Exception as e:
            return {"ok": False, "compile_returncode": 0,
                    "error": f"failed to launch simulator: {e}"}

    # E1 (audit): compile errors live in comp.log, runtime in sim.log.
    log = ""
    if sim_proc is not None and simlog.exists():
        log = simlog.read_text(errors="ignore")
    from .eda_log_analyzer import analyze_text
    if log:
        analysis = analyze_text(log, kind="vcs_uvm_sim", source=str(simlog))
    elif complog.exists() and (complog_text := complog.read_text(errors="ignore")):
        analysis = analyze_text(complog_text, kind="vcs_compile",
                                source=str(complog))
        log = complog_text
    elif sim_proc is not None and (sim_output :=
                                   (sim_proc.stdout + sim_proc.stderr).strip()):
        log = sim_output
        analysis = analyze_text(log, kind="vcs_uvm_sim", source="VCS stdout")
    else:
        analysis = {
        "verdict": "UNKNOWN", "issues": [], "counts": {},
        "failure_class": "tool_error", "retry_strategy": "regenerate",
        "recommended": {"recipe": "simulation_run", "next_step": "re-run simulation"}}
    returncode = (sim_proc.returncode if sim_proc is not None
                  else compile_proc.returncode)
    result = {
        "ok": (compile_proc.returncode == 0 and sim_proc is not None
               and sim_proc.returncode == 0 and analysis["verdict"] == "PASS"),
        "returncode": returncode,
        "compile_returncode": compile_proc.returncode,
        "simulation_returncode": (sim_proc.returncode if sim_proc else None),
        "testname": testname,
        "analysis": analysis,
    }
    if not result["ok"]:
        result["error"] = f"simulation {analysis['verdict']} ({analysis['failure_class']})"
        result["log_tail"] = log[-800:]
    return result


def build_verdi_command(fsdb: str, signals: list[str] | None = None,
                        verdi_binary: str = "verdi") -> list[str]:
    cmd = [verdi_binary, "-nologo", "-ssf", fsdb]
    for s in signals or []:
        cmd += ["-s", s]
    return cmd


def open_verdi(fsdb: str, signals: list[str] | None = None) -> dict:
    disc = discover()
    if not disc["tools"]["verdi"]["available"]:
        return {
            "ok": False, "error": "Verdi not available on this host",
            "setup": disc["tools"]["verdi"]["setup"],
            "ready_command": shlex.join(build_verdi_command(fsdb, signals)),
        }
    verdi_binary = disc["tools"]["verdi"].get("path") or "verdi"
    cmd = build_verdi_command(fsdb, signals, verdi_binary=verdi_binary)
    try:
        subprocess.Popen(cmd, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "launched": cmd}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fsdb_inspect(fsdb: str, signal: str | None = None, time: int = 0) -> dict:
    """Read FSDB through the pynpi execution layer (npi_tools) — a thin
    compatibility wrapper: inventory (time scale) + optional value at time.
    Single implementation of the runner; degrades with the unified contract
    when a real Verdi install is absent."""
    if not Path(fsdb).exists():
        return {"ok": False, "error": f"fsdb not found: {fsdb}"}
    from .npi_tools import _npi_eval, _open_close
    if signal:
        expr = ("{'time_scale': w.time_scale_unit(f), 'value':"
                f" w.sig_value_at(f, {signal!r}, {int(time)},"
                " w.VctFormat_e.HexStrVal)}")
    else:
        expr = "{'time_scale': w.time_scale_unit(f)}"
    res = _npi_eval(_open_close(fsdb, expr))
    if res.get("ok"):
        res["fsdb"] = fsdb
    return res


