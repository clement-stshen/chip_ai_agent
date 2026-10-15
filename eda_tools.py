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
import shutil
import subprocess
from pathlib import Path

MODULEFILES = [
    "/usr/share/Modules/modulefiles/synopsys",
    "/tools/Synopsys/scl/modulefile",
]
COMMON_ROOTS = ["/tools/Synopsys", "/eda/synopsys", "/opt/synopsys"]
NPI_ROOT = Path("/tools/Synopsys/temp/NPI")
TEMPLATE_ROOT = Path("/tools/lsf_api/uvm_tb")

# -- UVM reference library (Accellera, /tools/Synopsys/temp/uvm) -------------
# 6 releases ship unpacked next to their tarballs; the 1.x tarballs live in
# the parent dir, the 1800.2 ones inside uvm/. The project standard is the
# IEEE 1800.2-2020.3.1 kit. uvm-core-2020.3.1 is an identical twin (the
# "core" suffix is the Accellera GitHub repo name, not a feature subset).
UVM_ROOT = Path("/tools/Synopsys/temp/uvm")
UVM_TARBALLS: dict[str, Path] = {
    "uvm-1.0p1": Path("/tools/Synopsys/temp/uvm-1.0p1.tar.gz"),
    "uvm-1.1d": Path("/tools/Synopsys/temp/uvm-1.1d.tar.gz"),
    "uvm-1.2": Path("/tools/Synopsys/temp/uvm-1.2.tar.gz"),
    "1800.2-2020-2.0": UVM_ROOT / "UVM-18002-2020-20tar.gz",
    "1800.2-2020.3.1": UVM_ROOT / "UVM-1800.2-2020.3.1.tar.gz",
    "uvm-core-2020.3.1": UVM_ROOT / "uvm-core-2020.3.1.tar.gz",
}
DEFAULT_UVM_VERSION = "1800.2-2020.3.1"


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
    npi = {
        "kit_exists": NPI_ROOT.exists(),
        "pynpi_importable": (NPI_ROOT / "python/pynpi/__init__.py").exists(),
        "waveform_requires": "valid $VERDI_HOME (binary install)",
        "demo_fsdb": str(next(NPI_ROOT.glob(
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
    # pynpi-backed waveform layer: kit importable now, activation gated on a
    # real Verdi install (npisys.init requires $VERDI_HOME/bin/npi)
    from .npi_tools import NPI_PY, NPI_ROOT as _NPI_KIT, npi_available
    npi = {
        "kit": str(_NPI_KIT),
        "pynpi_py": str(NPI_PY),
        "importable": (NPI_PY / "pynpi").exists(),
        "ready": npi_available(),
        "requires": "real Verdi install ($VERDI_HOME/bin/npi) via "
                    "module load synopsys on EDA hosts",
    }
    # Synopsys verif-agent-mcp (4 VCS/URG/ipvgen tools): stdio adapter target
    va_venv = Path("/opt/verif-agent-mcp/venv/bin/verif-agent-mcp")
    va_cfg = Path("/etc/verif-agent-mcp/config.yaml")
    verif_agent = {
        "installed": va_venv.exists(),
        "config": str(va_cfg) if va_cfg.exists() else None,
        "stdio_command": (f"VERIF_AGENT_TRANSPORT=stdio VERIF_AGENT_BACKEND=stub "
                          f"{va_venv}") if va_venv.exists() else None,
    }
    return {"tools": tools, "modulefile_homes": homes, "npi": npi, "uvm": uvm,
            "verif_agent_mcp": verif_agent,
            "summary": f"vcs={'OK' if tools['vcs']['available'] else 'missing'} "
                       f"verdi={'OK' if tools['verdi']['available'] else 'missing'} "
                       f"npi={'ready' if npi['ready'] else 'kit-only'} "
                       f"uvm_libs={len(uvm['available'])}"}


def build_vcs_command(project_root: str, testname: str = "fifo_smoke_test") -> list[str]:
    """Standard VCS compile+run command for a UVM testbench project."""
    root = Path(project_root)
    uvm_home = resolve_uvm_home(project_root)
    filelist = root / "sim/filelist.f"
    return [
        "vcs", "-full64", "-sverilog", "-timescale=1ns/1ps", "-debug_access+all",
        f"+incdir+{uvm_home}/src", f"-f{filelist}", "-l", "comp.log", "-o", "simv",
        "&&", f"./simv", f"+UVM_TESTNAME={testname}",
        "+UVM_VERBOSITY=UVM_LOW", "-l", "sim.log",
    ]


def run_simulation(project_root: str, testname: str = "fifo_smoke_test",
                   timeout: int = 600) -> dict:
    """Compile + run a UVM simulation with VCS; parse the UVM report."""
    disc = discover()
    if not disc["tools"]["vcs"]["available"]:
        cmd = build_vcs_command(project_root, testname)
        return {
            "ok": False,
            "error": "VCS not available on this host",
            "setup": disc["tools"]["vcs"]["setup"],
            "declared_home": disc["tools"]["vcs"].get("declared_home"),
            "ready_command": "cd %s/sim && %s" % (project_root, " ".join(cmd)),
            "note": "run on the EDA host / LSF compute node after module load",
        }
    root = Path(project_root) / "sim"
    cmd = build_vcs_command(project_root, testname)
    try:
        proc = subprocess.run(" ".join(cmd), shell=True, cwd=root,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"simulation timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": f"failed to launch: {e}"}
    log = ""
    simlog = root / "sim.log"
    if simlog.exists():
        log = simlog.read_text(errors="ignore")
    from .eda_log_analyzer import analyze_text
    analysis = analyze_text(log, kind="vcs_uvm_sim", source=str(simlog)) if log else {
        "verdict": "UNKNOWN", "issues": [], "counts": {},
        "failure_class": "tool_error", "retry_strategy": "regenerate",
        "recommended": {"recipe": "simulation_run", "next_step": "re-run simulation"}}
    result = {
        "ok": proc.returncode == 0 and analysis["verdict"] == "PASS",
        "returncode": proc.returncode, "testname": testname,
        "analysis": analysis,
    }
    if not result["ok"]:
        result["error"] = f"simulation {analysis['verdict']} ({analysis['failure_class']})"
        result["log_tail"] = log[-800:]
    return result


def build_verdi_command(fsdb: str, signals: list[str] | None = None) -> list[str]:
    cmd = ["verdi", "-nologo", "-ssf", fsdb]
    for s in signals or []:
        cmd += ["-s", s]
    return cmd


def open_verdi(fsdb: str, signals: list[str] | None = None) -> dict:
    disc = discover()
    if not disc["tools"]["verdi"]["available"]:
        return {
            "ok": False, "error": "Verdi not available on this host",
            "setup": disc["tools"]["verdi"]["setup"],
            "ready_command": " ".join(build_verdi_command(fsdb, signals)),
        }
    cmd = build_verdi_command(fsdb, signals)
    try:
        subprocess.Popen(cmd, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "launched": cmd}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fsdb_inspect(fsdb: str, signal: str | None = None, time: int = 0) -> dict:
    """Read FSDB through pynpi when a real VERDI_HOME is configured."""
    if not Path(fsdb).exists():
        return {"ok": False, "error": f"fsdb not found: {fsdb}"}
    verdi_home = os.environ.get("VERDI_HOME", "")
    npi_py = NPI_ROOT / "python"
    npi_lib = NPI_ROOT / "lib/linux64"
    if not (verdi_home and Path(verdi_home).exists()):
        return {
            "ok": False,
            "error": "pynpi waveform DB requires a valid $VERDI_HOME",
            "setup": "module load synopsys (or set VERDI_HOME to the Verdi install)",
            "env_needed": {"VERDI_HOME": "...", "LD_LIBRARY_PATH": str(npi_lib),
                           "PYTHONPATH": str(npi_py)},
        }
    code = (
        "import os, json\n"
        "from pynpi import npisys, wave\n"
        "npisys.init([])\n"
        "f = wave.open(%r)\n"
        "assert f, 'open failed'\n"
        "out = {'time_scale': wave.time_scale_unit(f)}\n"
        + (f"out['value'] = wave.sig_value_at(f, {signal!r}, {time})\n" if signal else "")
        + "wave.close(f); npisys.end()\n"
        "print(json.dumps(out))\n"
    ) % (fsdb,)
    env = dict(os.environ, LD_LIBRARY_PATH=str(npi_lib), PYTHONPATH=str(npi_py))
    try:
        proc = subprocess.run(["python3", "-c", code], capture_output=True,
                              text=True, timeout=60, env=env)
        if proc.returncode == 0:
            return {"ok": True, "fsdb": fsdb, **json.loads(proc.stdout.strip().splitlines()[-1])}
        return {"ok": False, "error": proc.stderr.strip()[-400:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


