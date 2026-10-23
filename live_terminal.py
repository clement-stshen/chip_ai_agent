"""
Global live terminal for VCS compile and simulation.

Three monitoring channels (all automatic, no user setup needed):
  1. LIVE LOG FILE    — /tmp/chip_agent_live.log (tail -f to watch)
  2. STDOUT           — captured by exec_command (tool result)
  3. TMUX SESSION     — chip_live session (tmux attach -t chip_live)

Usage:
    from chip_ai_agent.live_terminal import LiveRun
    lr = LiveRun()
    result = lr.run_compile([...], cwd="...")
    # → live log file updated in real-time
    # → user watches: tail -f /tmp/chip_agent_live.log
    # → or: tmux attach -t chip_live
"""

import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# ─── Global live log file (user watches with tail -f) ───
# Live log path from site config (overridable via env)
try:
    from .site_paths import LIVE_LOG as LIVE_LOG
except ImportError:
    LIVE_LOG = os.environ.get("CHIP_AGENT_LIVE_LOG", "/tmp/chip_agent_live.log")
LIVE_LOG_PATH = Path(LIVE_LOG)

# ─── ANSI colors ───
class C:
    RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
    BLUE="\033[34m"; MAGENTA="\033[35m"; CYAN="\033[36m"; WHITE="\033[37m"
    BG_RED="\033[41m"; BG_GREEN="\033[42m"

_PATTERNS = [
    (re.compile(r"UVM_FATAL",re.I),          C.BG_RED+C.WHITE+C.BOLD,  True, "FATAL"),
    (re.compile(r"UVM_ERROR",re.I),           C.RED+C.BOLD,             True, "ERROR"),
    (re.compile(r"UVM_WARNING",re.I),         C.YELLOW,                 True, "WARN"),
    (re.compile(r"UVM_INFO.*RNTST",re.I),     C.CYAN+C.BOLD,            True, "TEST"),
    (re.compile(r"TEST PASSED",re.I),         C.BG_GREEN+C.WHITE+C.BOLD,True, "PASS"),
    (re.compile(r"TEST FAILED",re.I),         C.BG_RED+C.WHITE+C.BOLD,  True, "FAIL"),
    (re.compile(r"Error-\[",re.I),            C.RED,                    True, "ERROR"),
    (re.compile(r"Warning-\[",re.I),          C.YELLOW,                 False,"WARN"),
    (re.compile(r"FIFO_SVA|SVA.*assert",re.I),C.MAGENTA,               True, "SVA"),
    (re.compile(r"UVM_REPORT|report_phase",re.I),C.CYAN+C.BOLD,         True, "REPORT"),
    (re.compile(r"build_phase|connect_phase|run_phase",re.I),C.BLUE,  False,"PHASE"),
    (re.compile(r"Coverage|coverage",re.I),   C.GREEN,                  False,"COV"),
    (re.compile(r"CPU time|simv up to date",re.I),C.GREEN,              True, "DONE"),
    (re.compile(r"scoreboard|score",re.I),    C.GREEN,                  True, "SCORE"),
]

def classify(line):
    for pat, color, imp, label in _PATTERNS:
        if pat.search(line):
            return color, imp, label
    return "", False, ""


class LiveRun:
    """Execute command with live output to: file + stdout + tmux."""

    def __init__(self, verbose=True, show_all=False, max_display=500,
                 live_log=None, use_tmux=True):
        self.verbose = verbose
        self.show_all = show_all
        self.max_display = max_display
        self.live_log = live_log or LIVE_LOG
        self.use_tmux = use_tmux
        self._count = 0
        # Initialize live log
        LIVE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _write_live(self, line, color="", label=""):
        """Write to live log file (user watches with tail -f)."""
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            if label:
                with open(self.live_log, "a") as f:
                    f.write(f"[{ts}] {label:>8s} | {line}\n")
            else:
                with open(self.live_log, "a") as f:
                    f.write(f"[{ts}] {line}\n")
        except Exception:
            pass

    def _print(self, line, color="", label=""):
        """Print to stdout (captured by exec_command tool)."""
        if not self.verbose:
            return
        if self._count >= self.max_display and not self.show_all:
            return
        self._count += 1
        if color:
            print(f"{color}{label:>8s} | {line}{C.RESET}", flush=True)
        else:
            print(line, flush=True)

    def _should_show(self, line):
        if self.show_all:
            return True
        if self._count >= self.max_display:
            return False
        _, imp, _ = classify(line)
        if imp:
            return True
        s = line.strip()
        if not s:
            return False
        for skip in ("UVM_NO_DEPRECATED","UVM_OBJECT_DO_NOT","eda.org/svdb",
                     "RELNOTES","proprietary information","license agreement",
                     "Host System","ASLR","VCS_SAVE_RESTORE"):
            if skip in line:
                return False
        return True

    def run(self, command, cwd=".", label="RUN", timeout=120, env=None):
        """Execute with live output to 3 channels: file + stdout + tmux."""
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        # Clear/initialize live log for this run
        header = (f"{'='*60}\n"
                  f"  {label}\n"
                  f"  $ {' '.join(command)}\n"
                  f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                  f"{'='*60}\n")
        with open(self.live_log, "w") as f:
            f.write(header)

        # Print header to stdout
        if self.verbose:
            print(f"\n{'─'*60}")
            print(f"▶ {label}")
            print(f"$ {' '.join(command)}")
            print(f"📺 Live monitor: tail -f {self.live_log}")
            if self.use_tmux:
                print(f"📺 tmux: tmux attach -t chip_live 2>/dev/null")
            print(f"{'─'*60}")

        # Start tmux session for real-time terminal (if available)
        tmux_proc = None
        if self.use_tmux:
            try:
                # Kill existing session, create new one running tail -f
                subprocess.run(["tmux","kill-session","-t","chip_live"],
                             capture_output=True, timeout=2)
                tmux_cmd = f"tail -f {self.live_log}"
                tmux_proc = subprocess.Popen(
                    ["tmux","new-session","-d","-s","chip_live","-x","120","-y","40",
                     "bash","-c", tmux_cmd],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.3)  # let tmux start
            except Exception:
                tmux_proc = None

        self._count = 0
        start = time.time()
        output_lines = []
        timed_out = False

        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, cwd=cwd, env=run_env,
                bufsize=1, text=True, errors="replace")

            for line in proc.stdout:
                line = line.rstrip("\n\r")
                output_lines.append(line)

                color, imp, lbl = classify(line)
                # Write to live log file (ALL lines)
                self._write_live(line, color, lbl)
                # Print to stdout (filtered)
                if self._should_show(line):
                    self._print(line, color, lbl)

                if time.time() - start > timeout:
                    proc.send_signal(signal.SIGTERM)
                    timed_out = True
                    timeout_msg = f"⏱ TIMEOUT after {timeout}s"
                    self._write_live(timeout_msg, C.YELLOW, "TIMEOUT")
                    self._print(timeout_msg, C.YELLOW, "TIMEOUT")
                    break

            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(); timed_out = True
        except FileNotFoundError:
            msg = f"❌ Command not found: {command[0]}"
            self._write_live(msg, C.RED, "ERROR")
            self._print(msg, C.RED, "ERROR")
            return {"exit_code":-1,"output":"not found","lines":0,"duration_s":0,
                    "verdict":"ERROR","uvm_error":0,"uvm_fatal":0,
                    "uvm_warning":0,"timed_out":False,"label":label,
                    "command":" ".join(command)}

        duration = time.time() - start
        full = "\n".join(output_lines)
        exit_code = proc.returncode if not timed_out else -1

        uvm_err = len(re.findall(r"UVM_ERROR", full))
        uvm_fatal = len(re.findall(r"UVM_FATAL", full))
        uvm_warn = len(re.findall(r"UVM_WARNING", full))
        has_pass = "TEST PASSED" in full
        has_fail = "TEST FAILED" in full

        if timed_out: verdict = "TIMEOUT"
        elif has_pass: verdict = "PASS"
        elif has_fail: verdict = "FAIL"
        elif uvm_fatal > 0: verdict = "FAIL"
        elif exit_code == 0: verdict = "PASS"
        else: verdict = "ERROR"

        # Footer
        footer = (f"{'─'*60}\n"
                  f"  {verdict} | {label} | {duration:.1f}s | "
                  f"{len(output_lines)} lines | err={uvm_err} fatal={uvm_fatal}\n"
                  f"{'─'*60}\n")
        self._write_live(footer)
        if self.verbose:
            vc = {"PASS":C.GREEN,"FAIL":C.RED,"TIMEOUT":C.YELLOW,"ERROR":C.RED}.get(verdict,C.WHITE)
            vi = {"PASS":"✅","FAIL":"❌","TIMEOUT":"⏱","ERROR":"💥"}.get(verdict,"?")
            print(f"\n{vc}{C.BOLD}{vi} {label} → {verdict} "
                  f"({duration:.1f}s, {len(output_lines)} lines, "
                  f"err={uvm_err}, fatal={uvm_fatal}){C.RESET}")
            print(f"📺 Full log: tail -f {self.live_log}")

        # Cleanup tmux
        if tmux_proc:
            try:
                tmux_proc.terminate()
            except: pass

        return {
            "exit_code": exit_code, "output": full,
            "lines": len(output_lines), "duration_s": round(duration,1),
            "verdict": verdict, "uvm_error": uvm_err,
            "uvm_fatal": uvm_fatal, "uvm_warning": uvm_warn,
            "timed_out": timed_out, "label": label,
            "command": " ".join(command),
        }

    def run_compile(self, args, cwd, env=None):
        return self.run(args, cwd=cwd, label="VCS Compile", timeout=60, env=env)

    def run_sim(self, simv, testname, cwd, seed=1, coverage=True,
                cm_name=None, timeout=60, env=None):
        args = [simv, f"+UVM_TESTNAME={testname}",
                "+UVM_VERBOSITY=UVM_MEDIUM", f"+ntb_random_seed={seed}"]
        if coverage:
            args += ["-cm","line+cond+fsm+tgl+branch+assert"]
            if cm_name:
                args += ["-cm_dir",f"cov_{cm_name}.vdb","-cm_name",cm_name]
        return self.run(args, cwd=cwd,
                       label=f"Sim {testname} seed={seed}", timeout=timeout, env=env)


def get_monitor_command():
    """Return the command the user should run to watch live output."""
    return f"tail -f {LIVE_LOG}"


def get_tmux_command():
    """Return the command to attach to the tmux live session."""
    return "tmux attach -t chip_live"
