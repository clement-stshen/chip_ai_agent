"""Local pynpi-backed execution layer for the Verdi waveform skill surface.

Deep-kit analysis facts (/tools/Synopsys/temp/NPI):
  - pynpi (SWIG 4.0.2) ships compiled .so modules whose RUNPATH is
    $ORIGIN/.., so ONLY PYTHONPATH=NPI/python is needed — no
    LD_LIBRARY_PATH. Verified importable on the venv python 3.12.
  - npisys.init() gates on a REAL Verdi install: the library opens
    $VERDI_HOME/bin/npi for reading. We never fabricate that file —
    activation requires a genuine `module load synopsys` on an EDA host.
  - waveform.py: open/info/sig_value_at/sig_value_between/
    sig_find_value_forward/backward/sig_find_x_forward/backward/
    sig_vc_count + FileHandle/ScopeHandle/SigHandle/VctHandle
    (time/value/goto_first/next/prev/time, duration(), seq_num()).
  - wave_l1.py: SigValueEval expression evaluator (evaluate/get_posedge/
    get_negedge) — sequence and latency computations.
  - Design-side skills (module definitions, ports, source mapping) need
    npisys.load_design + a VCS-compiled DB and keep their degrade paths;
    hierarchy views are approximated from the FSDB scope tree, and file
    reads are plain I/O.

Every tool degrades gracefully without Verdi:
    {ok: False, error, setup, env_needed, ready_command}
identical to the existing run_simulation/fsdb_inspect contract.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

from .site_paths import NPI_ROOT, NPI_PY, NPI_LIB

_SETUP_HINT = "module load synopsys   # or set VERDI_HOME to the Verdi install"


def npi_available() -> bool:
    """True when a genuine Verdi install gates pynpi init: the library itself
    requires a readable $VERDI_HOME/bin/npi, so we check exactly that."""
    verdi = os.environ.get("VERDI_HOME", "")
    return bool(verdi) and (Path(verdi) / "bin" / "npi").is_file()


def _degrade(what: str = "pynpi waveform access") -> dict:
    return {
        "ok": False,
        "error": f"{what} requires a real Verdi install (pynpi init gate)",
        "setup": _SETUP_HINT,
        "env_needed": {"VERDI_HOME": "...", "PYTHONPATH": str(NPI_PY)},
        "ready_command": "VERDI_HOME=<verdi> PYTHONPATH=%s python3 ..." % NPI_PY,
    }


_BOOT = (
    "import json\n"
    "from pynpi import npisys\n"
    "npisys.init([])\n"
)


def _npi_eval(code: str, timeout: int = 60) -> dict:
    """One-shot pynpi subprocess; the payload's last stdout line is JSON.
    Injectable in tests via the tools' _eval parameter."""
    if not npi_available():
        return _degrade()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _BOOT + code],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(NPI_PY)})
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"pynpi timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": f"failed to launch pynpi: {e}"}
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip()[-400:]}
    out = proc.stdout.strip().splitlines()
    if not out:
        return {"ok": False, "error": "pynpi produced no output"}
    try:
        payload = json.loads(out[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": f"bad pynpi payload: {out[-1][:200]}"}
    return {"ok": True, **payload}


def _open_close(fsdb: str, expr: str, pre: str = "") -> str:
    """Code template: open FSDB, run pre + expr, close; payload printed as
    the last stdout line (json.dumps of the expr value)."""
    return (
        "from pynpi import waveform as w\n"
        "f = w.open(%r)\n"
        "assert f, 'open failed'\n"
        "try:\n"
        "%s"
        "    print(json.dumps(%s))\n"
        "finally:\n"
        "    w.close(f)\n" % (fsdb, pre, expr)
    )


def _indent(code: str, pad: str = "    ") -> str:
    return "".join(pad + ln + "\n" for ln in code.splitlines() if ln.strip())


_HEX = "w.VctFormat_e.HexStrVal"


def _check_fsdb(args: dict) -> dict | None:
    fsdb = args.get("fsdb") or args.get("path")
    if not fsdb:
        return {"ok": False, "error": "fsdb path required"}
    if not Path(fsdb).exists():
        return {"ok": False, "error": f"fsdb not found: {fsdb}"}
    args["fsdb"] = str(fsdb)
    return None


# ---------------------------------------------------------------------------
# stateless query tools (one-shot subprocess per call)
# ---------------------------------------------------------------------------

def load_fsdb(args: dict, _eval=None) -> dict:
    """Validate an FSDB and return its inventory (time range, scale, top
    scopes). Session tracking (get/set_active_fsdb) lives in NpiWorker."""
    err = _check_fsdb(args)
    if err:
        return err
    ev = _eval or _npi_eval
    code = _open_close(args["fsdb"], (
        "{'info': w.info(f.name()), 'top_scopes':"
        " [s.name() for s in f.top_scope_list()][:50]}"))
    return ev(code)


def list_signals(args: dict, _eval=None) -> dict:
    """Signals under a scope (default top), depth-limited recursion."""
    err = _check_fsdb(args)
    if err:
        return err
    scope = args.get("scope")
    depth = int(args.get("depth", 1))
    fsdb = args["fsdb"]
    pre = (
        "root = f.scope_by_name(%r) or f.top_scope_list()[0]\n"
        "out = {'scopes': {}}\n"
        "def walk(s, d):\n"
        "    out['scopes'][s.full_name()] = [x.name() for x in s.sig_list()]\n"
        "    if d > 0:\n"
        "        for c in s.child_scope_list():\n"
        "            walk(c, d - 1)\n"
        "walk(root, %d)\n" % (scope, depth))
    ev = _eval or _npi_eval
    return ev(_open_close(fsdb, "out", _indent(pre)))


def list_signals_in_scope(args: dict, _eval=None) -> dict:
    """All signals reachable from a scope (recursive)."""
    args = dict(args)
    args["depth"] = args.get("depth", 32)
    return list_signals(args, _eval=_eval)


def get_signal_value_at_time(args: dict, _eval=None) -> dict:
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    t = int(args.get("time", 0))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"],
                          f"w.sig_value_at(f, {sig!r}, {t}, {_HEX})"))


def get_first_value(args: dict, _eval=None) -> dict:
    return _value_at_boundary(args, "first", _eval)


def get_last_value(args: dict, _eval=None) -> dict:
    return _value_at_boundary(args, "last", _eval)


def _value_at_boundary(args: dict, which: str, _eval) -> dict:
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    ev = _eval or _npi_eval
    if which == "first":
        expr = (f"(lambda s: {{'time': w.sig_hdl_value_at(s, f.min_time(),"
                f" {_HEX})}})(f.sig_by_name({sig!r}))")
    else:
        expr = (f"(lambda s: {{'time': w.sig_hdl_value_at(s, f.max_time(),"
                f" {_HEX})}})(f.sig_by_name({sig!r}))")
    # sig_hdl_value_at returns the VALUE; wrap with the queried boundary time
    expr = (f"{{'time': f.min_time(), 'value': {expr}}}" if which == "first"
            else f"{{'time': f.max_time(), 'value': {expr}}}")
    return ev(_open_close(args["fsdb"], expr))


def find_signal_transition_to_value(args: dict, _eval=None) -> dict:
    err = _check_fsdb(args)
    if err:
        return err
    sig, value = args.get("signal"), args.get("value")
    if not sig or value is None:
        return {"ok": False, "error": "signal + value required"}
    t = int(args.get("time", 0))
    fn = ("sig_find_value_forward" if args.get("direction", "forward") == "forward"
          else "sig_find_value_backward")
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"],
                          f"w.{fn}(f, {sig!r}, {value!r}, {t}, {_HEX})"))


def find_signal_value_change_event(args: dict, _eval=None) -> dict:
    """Nearest value change at/after `time` for a signal."""
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    t = int(args.get("time", 0))
    pre = (
        "s = f.sig_by_name(%r)\n"
        "assert s, 'signal not found'\n"
        "v = s.create_vct()\n"
        "v.goto_time(%d)\n"
        "if v.time() < %d:\n"
        "    v.goto_next()\n"
        "out = {'time': v.time(), 'value': v.value(%s),"
        " 'seq_num': v.seq_num()}\n" % (sig, t, t, _HEX))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def find_nth_transition_of_signal(args: dict, _eval=None) -> dict:
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    n = max(int(args.get("n", 1)), 1)
    pre = (
        "s = f.sig_by_name(%r)\n"
        "assert s, 'signal not found'\n"
        "v = s.create_vct()\n"
        "v.goto_first()\n"
        "for _ in range(%d - 1):\n"
        "    v.goto_next()\n"
        "out = {'n': %d, 'time': v.time(), 'value': v.value(%s)}\n"
        % (sig, n, n, _HEX))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def calculate_signal_duration(args: dict, _eval=None) -> dict:
    """Duration of the value active at `time` (VctHandle.duration)."""
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    t = int(args.get("time", 0))
    pre = (
        "s = f.sig_by_name(%r)\n"
        "assert s, 'signal not found'\n"
        "v = s.create_vct()\n"
        "v.goto_time(%d)\n"
        "out = {'time': v.time(), 'duration': v.duration()}\n" % (sig, t))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def get_signal_switching_statistics(args: dict, _eval=None) -> dict:
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    pre = (
        "s = f.sig_by_name(%r)\n"
        "assert s, 'signal not found'\n"
        "pairs = w.sig_value_between(f, %r, f.min_time(), f.max_time())\n"
        "out = {'vc_count': w.sig_vc_count(f, %r, f.min_time(), f.max_time()),\n"
        "       'dwell': {}, 'value_count': len(pairs)}\n"
        "for i, (t, v) in enumerate(pairs):\n"
        "    dt = (pairs[i+1][0] - t) if i + 1 < len(pairs) else 0\n"
        "    out['dwell'][str(v)] = out['dwell'].get(str(v), 0) + dt\n"
        % (sig, sig, sig))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def detect_unknown_and_get_previous_or_next_transitions(args: dict, _eval=None) -> dict:
    err = _check_fsdb(args)
    if err:
        return err
    sig = args.get("signal")
    if not sig:
        return {"ok": False, "error": "signal name required"}
    t = int(args.get("time", 0))
    direction = args.get("direction", "forward")
    fn = "sig_find_x_forward" if direction == "forward" else "sig_find_x_backward"
    pre = (
        "x = w.%s(f, %r, %d)\n"
        "out = {'x_time': x}\n"
        "if x is not None:\n"
        "    s = f.sig_by_name(%r)\n"
        "    v = s.create_vct(); v.goto_time(x)\n"
        "    v.goto_prev()\n"
        "    out['previous'] = {'time': v.time(), 'value': v.value(%s)}\n"
        % (fn, sig, t, sig, _HEX))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def detect_signal_sequence(args: dict, _eval=None) -> dict:
    """True-time ranges of a boolean expression over signals (SigValueEval)."""
    err = _check_fsdb(args)
    if err:
        return err
    expr = args.get("expression") or args.get("expr")
    if not expr:
        return {"ok": False, "error": "expression required (e.g. 'a && b')"}
    pre = (
        "from pynpi import wave_l1\n"
        "ev = wave_l1.SigValueEval()\n"
        "ev.set_wave(f)\n"
        "ev.set_expr(%r)\n"
        "rc, tv = ev.evaluate(timeValueMode=True)\n"
        "out = {'rc': int(rc), 'true_times': tv[:200]}\n" % expr)
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def get_max_latency(args: dict, _eval=None) -> dict:
    """Max latency between value changes of two signals (edge-pair walk)."""
    err = _check_fsdb(args)
    if err:
        return err
    a, b = args.get("signal_a") or args.get("signal"), args.get("signal_b")
    if not a or not b:
        return {"ok": False, "error": "signal_a + signal_b required"}
    pre = (
        "pa = w.sig_value_between(f, %r, f.min_time(), f.max_time())\n"
        "pb = w.sig_value_between(f, %r, f.min_time(), f.max_time())\n"
        "i = j = best = 0\n"
        "while i < len(pa) - 1 and j < len(pb) - 1:\n"
        "    d = pb[j+1][0] - pa[i][0]\n"
        "    if 0 <= d:\n"
        "        best = max(best, d)\n"
        "    if pa[i+1][0] < pb[j+1][0]:\n"
        "        i += 1\n"
        "    else:\n"
        "        j += 1\n"
        "out = {'max_latency': best}\n" % (a, b))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def list_instances_in_hierarchy(args: dict, _eval=None) -> dict:
    """Instance tree approximated from the FSDB scope tree (def names)."""
    err = _check_fsdb(args)
    if err:
        return err
    pre = (
        "out = {}\n"
        "def walk(s):\n"
        "    out[s.full_name()] = s.def_name()\n"
        "    for c in s.child_scope_list():\n"
        "        walk(c)\n"
        "for top in f.top_scope_list():\n"
        "    walk(top)\n")
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def show_hierarchy_tree(args: dict, _eval=None) -> dict:
    """Indented text tree of the FSDB scope hierarchy."""
    err = _check_fsdb(args)
    if err:
        return err
    pre = (
        "lines = []\n"
        "def walk(s, depth):\n"
        "    lines.append('  ' * depth + s.name() + '  (' + s.def_name() + ')')\n"
        "    for c in s.child_scope_list():\n"
        "        walk(c, depth + 1)\n"
        "for top in f.top_scope_list():\n"
        "    walk(top, 0)\n"
        "out = {'tree': lines}\n")
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


def add_signals(args: dict, _eval=None) -> dict:
    """Validate a selection of signals exists (nWave window emulation: the
    selection itself is client-side)."""
    err = _check_fsdb(args)
    if err:
        return err
    sigs = args.get("signals") or []
    if not sigs:
        return {"ok": False, "error": "signals list required"}
    pre = (
        "missing = []\n"
        "for name in %r:\n"
        "    if f.sig_by_name(name) is None:\n"
        "        missing.append(name)\n"
        "out = {'selected': %r, 'missing': missing}\n" % (list(sigs), list(sigs)))
    ev = _eval or _npi_eval
    return ev(_open_close(args["fsdb"], "out", _indent(pre)))


# ---------------------------------------------------------------------------
# plain file-I/O tools (no pynpi needed)
# ---------------------------------------------------------------------------

def read_specific_lines(args: dict) -> dict:
    path = args.get("path") or args.get("file")
    if not path or not Path(path).exists():
        return {"ok": False, "error": f"file not found: {path}"}
    start = int(args.get("start", 1))
    count = int(args.get("count", 20))
    lines = Path(path).read_text(errors="ignore").splitlines()
    return {"ok": True, "path": path, "total_lines": len(lines),
            "lines": [{"no": i, "text": ln}
                      for i, ln in enumerate(lines[start - 1:start - 1 + count],
                                             start)]}


def search_in_source_code_result(args: dict) -> dict:
    """Search text files (a previous source dump or any .sv/.v list)."""
    path = args.get("path") or args.get("file")
    pattern = args.get("pattern") or args.get("query")
    if not path or not Path(path).exists():
        return {"ok": False, "error": f"file not found: {path}"}
    if not pattern:
        return {"ok": False, "error": "pattern required"}
    hits = []
    for i, ln in enumerate(Path(path).read_text(errors="ignore").splitlines(), 1):
        if pattern in ln:
            hits.append({"line": i, "text": ln[:200]})
    return {"ok": True, "path": path, "pattern": pattern,
            "matches": hits[:100], "match_count": len(hits)}


# ---------------------------------------------------------------------------
# session tools: persistent pynpi worker (load/get_active/set_active_fsdb)
# ---------------------------------------------------------------------------

# worker session state (module-level, per-process: one worker = one session)
_WORKER_STATE: dict = {"opened": {}, "active": None}


def worker_dispatch(cmd: dict, mod) -> dict:
    """Worker command dispatcher; `mod` is the pynpi module facade
    (injectable for tests). Holds opened FSDB handles + the active name."""
    name = cmd.get("cmd")
    opened = _WORKER_STATE["opened"]
    if name == "open":
        fsdb = cmd.get("fsdb")
        f = mod.waveform.open(fsdb) if hasattr(mod, "waveform") else mod.open(fsdb)
        if f is None:
            return {"ok": False, "error": f"open failed: {fsdb}"}
        opened[fsdb] = f
        info = mod.waveform.info(fsdb) if hasattr(mod, "waveform") else {}
        return {"ok": True, "fsdb": fsdb, "info": info}
    if name == "active":
        return {"ok": True, "active": _WORKER_STATE["active"]}
    if name == "set_active":
        fsdb = cmd.get("fsdb")
        if fsdb not in opened:
            return {"ok": False, "error": f"not opened: {fsdb}"}
        _WORKER_STATE["active"] = fsdb
        return {"ok": True, "active": fsdb}
    if name == "close":
        fsdb = cmd.get("fsdb") or _WORKER_STATE["active"]
        f = opened.pop(fsdb, None)
        if f is not None:
            mod.waveform.close(f)
        if _WORKER_STATE["active"] == fsdb:
            _WORKER_STATE["active"] = None
        return {"ok": True, "closed": fsdb}
    if name == "exit":
        for f in opened.values():
            try:
                mod.waveform.close(f)
            except Exception:
                pass
        opened.clear()
        _WORKER_STATE["active"] = None
        return {"ok": True, "bye": True}
    return {"ok": False, "error": f"unknown worker cmd: {name}"}


def _worker_main() -> int:
    """Worker entry: JSON-line loop over real pynpi (spawned by NpiWorker)."""
    import json as _json
    from pynpi import npisys
    npisys.init([])
    import pynpi as mod
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        resp = {"id": req.get("id"), **worker_dispatch(req, mod)}
        sys.stdout.write(_json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if resp.get("bye"):
            return 0
    return 0


class NpiWorker:
    """Persistent pynpi session process (spawned only when npi_available)."""

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self.proc = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._stdout_buffer = b""

    def _ensure(self) -> dict | None:
        """Spawn the worker; returns a degrade dict when Verdi is absent."""
        if not npi_available():
            return _degrade("session tools (load/get_active/set_active_fsdb)")
        if self.proc is not None:
            return None
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-u", "-c",
                 "import sys; sys.path.insert(0, %r);\n"
                 "from chip_ai_agent.npi_tools import _worker_main\n"
                 "sys.exit(_worker_main())\n" % str(Path(__file__).parent.parent)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                bufsize=0,
                env={**os.environ, "PYTHONPATH": str(NPI_PY)})
            self._stdout_buffer = b""
        except Exception as e:
            return {"ok": False, "error": f"failed to spawn npi worker: {e}"}
        return None

    def cmd(self, name: str, **kw) -> dict:
        with self._lock:
            err = self._ensure()
            if err:
                return err
            assert self.proc is not None
            mid = self._next_id
            self._next_id += 1
            self.proc.stdin.write(
                (json.dumps({"id": mid, "cmd": name, **kw}) + "\n").encode())
            self.proc.stdin.flush()
            try:
                deadline = time.monotonic() + self.timeout
                while True:
                    if b"\n" in self._stdout_buffer:
                        line, self._stdout_buffer = self._stdout_buffer.split(
                            b"\n", 1)
                        if not line.strip():
                            continue
                        resp = json.loads(line)
                        if resp.get("id") == mid:
                            resp.pop("id", None)
                            return resp
                        continue

                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select(
                            [self.proc.stdout], [], [], remaining)[0]:
                        self.close()
                        return {"ok": False,
                                "error": f"npi worker timed out after {self.timeout}s"}
                    chunk = os.read(self.proc.stdout.fileno(), 4096)
                    if not chunk:
                        self.close()
                        return {"ok": False, "error": "npi worker exited"}
                    self._stdout_buffer += chunk
            except Exception as e:
                self.close()
                return {"ok": False, "error": f"npi worker failed: {e}"}

    def close(self):
        proc, self.proc = self.proc, None
        self._stdout_buffer = b""
        if proc is not None:
            try:
                proc.stdin.write(b'{"id": 0, "cmd": "exit"}\n')
                proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


_WORKER: NpiWorker | None = None
_WORKER_LOCK = threading.Lock()


def _get_worker() -> NpiWorker:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None:
            _WORKER = NpiWorker()
        return _WORKER


def get_active_fsdb(args: dict) -> dict:
    return _get_worker().cmd("active")


def set_active_fsdb(args: dict) -> dict:
    fsdb = args.get("fsdb")
    if not fsdb:
        return {"ok": False, "error": "fsdb required"}
    return _get_worker().cmd("set_active", fsdb=fsdb)


def load_fsdb_session(args: dict) -> dict:
    """load_fsdb with real session semantics (persistent open handle)."""
    err = _check_fsdb(args)
    if err:
        return err
    return _get_worker().cmd("open", fsdb=args["fsdb"])
