"""High-performance scheduling layer for the chip verification agent.

Optimizations:
  1. Parallel RAG backend fan-out (ThreadPoolExecutor with per-backend timeout)
  2. Result memoization (TTL cache for all read-only tool calls)
  3. Dependency-aware step scheduling (DAG-based parallel execution)
  4. Early termination on upstream failure (skip dependents, save time)
  5. Warm index preload (background thread at server startup)
  6. Circuit breaker (skip tools that have failed N consecutive times)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# 1. Global result cache (TTL-based, LRU-bounded)
# ---------------------------------------------------------------------------

_CACHE: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = int(os.environ.get("CHIP_AGENT_SCHED_CACHE_MAX", "512"))
_CACHE_TTL = float(os.environ.get("CHIP_AGENT_SCHED_CACHE_TTL", "120"))


def _cache_key(tool: str, args: dict) -> str:
    raw = json.dumps({"t": tool, "a": args}, sort_keys=True, ensure_ascii=False)
    return hashlib.blake2b(raw.encode(), digest_size=16).hexdigest()


def cache_get(tool: str, args: dict) -> Any | None:
    if _CACHE_TTL <= 0:
        return None
    key = _cache_key(tool, args)
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        ts, val = entry
        if time.monotonic() - ts > _CACHE_TTL:
            del _CACHE[key]
            return None
        _CACHE.move_to_end(key)  # LRU touch
        return val


def cache_put(tool: str, args: dict, value: Any) -> None:
    if _CACHE_TTL <= 0 or not isinstance(value, dict) or "error" in value:
        return
    key = _cache_key(tool, args)
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def cache_clear() -> int:
    with _CACHE_LOCK:
        n = len(_CACHE)
        _CACHE.clear()
    return n


def cache_stats() -> dict:
    with _CACHE_LOCK:
        return {"entries": len(_CACHE), "max": _CACHE_MAX, "ttl": _CACHE_TTL}


# ---------------------------------------------------------------------------
# 2. Circuit breaker (skip tools with N consecutive failures)
# ---------------------------------------------------------------------------

_CB_THRESHOLD = int(os.environ.get("CHIP_AGENT_CB_THRESHOLD", "3"))
_CB_COOLDOWN = float(os.environ.get("CHIP_AGENT_CB_COOLDOWN", "60"))
_CB_STATE: dict[str, dict] = {}  # tool → {"consecutive_failures": N, "last_fail_ts": T, "open": bool}
_CB_LOCK = threading.Lock()


def cb_check(tool: str) -> bool:
    """Return True if the tool is healthy (circuit closed)."""
    with _CB_LOCK:
        state = _CB_STATE.get(tool)
        if state is None or not state.get("open"):
            return True
        # Check if cooldown has expired → half-open (allow one attempt)
        if time.monotonic() - state["last_fail_ts"] > _CB_COOLDOWN:
            state["open"] = False
            return True
        return False


def cb_record(tool: str, success: bool) -> None:
    with _CB_LOCK:
        state = _CB_STATE.setdefault(tool, {"consecutive_failures": 0, "last_fail_ts": 0, "open": False})
        if success:
            state["consecutive_failures"] = 0
            state["open"] = False
        else:
            state["consecutive_failures"] += 1
            state["last_fail_ts"] = time.monotonic()
            if state["consecutive_failures"] >= _CB_THRESHOLD:
                state["open"] = True


def cb_stats() -> dict:
    with _CB_LOCK:
        return {k: {"failures": v["consecutive_failures"], "open": v["open"]}
                for k, v in _CB_STATE.items()}


# ---------------------------------------------------------------------------
# 3. Parallel dispatch with timeout and caching
# ---------------------------------------------------------------------------

def dispatch_with_cache(handler: Callable, tool: str, args: dict,
                        timeout: float = 30.0) -> Any:
    """Single tool dispatch with cache lookup + circuit breaker + timeout."""
    # Cache hit
    cached = cache_get(tool, args)
    if cached is not None:
        return cached

    # Circuit breaker check
    if not cb_check(tool):
        return {"error": f"circuit breaker open for {tool}",
                "retry_after": _CB_COOLDOWN}

    # Dispatch with timeout
    result_container: dict = {"result": None, "exception": None}
    def _run():
        try:
            result_container["result"] = handler(args)
        except Exception as e:
            result_container["exception"] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        cb_record(tool, success=False)
        return {"error": f"{tool} timed out after {timeout}s", "retryable": True}

    if result_container["exception"]:
        cb_record(tool, success=False)
        return {"error": str(result_container["exception"]), "tool": tool}

    result = result_container["result"]
    is_err = isinstance(result, dict) and "error" in result
    cb_record(tool, success=not is_err)
    if not is_err:
        cache_put(tool, args, result)
    return result


def parallel_dispatch(tasks: list[dict],
                      max_workers: int = 4,
                      per_task_timeout: float = 30.0) -> list[dict]:
    """Execute multiple tool calls in parallel.

    Args:
        tasks: [{"tool": name, "args": {...}, "handler": callable}, ...]
        max_workers: ThreadPoolExecutor size
        per_task_timeout: Timeout per task in seconds

    Returns:
        Results in the same order as tasks.
        Each result dict gets an extra "_meta" key with timing info.
    """
    results: list[dict | None] = [None] * len(tasks)
    timings: list[float] = [0.0] * len(tasks)

    def _run_one(idx: int, task: dict) -> tuple[int, Any, float]:
        t0 = time.perf_counter()
        handler = task.get("handler")
        if handler is None:
            from .local_tools import call_local
            handler = lambda a, _t=task["tool"]: call_local(_t, a)
        res = dispatch_with_cache(handler, task["tool"], task.get("args", {}), per_task_timeout)
        return idx, res, time.perf_counter() - t0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, i, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures, timeout=per_task_timeout * 2):
            try:
                idx, res, dt = future.result()
                results[idx] = res
                timings[idx] = dt
            except Exception:
                idx = futures[future]
                results[idx] = {"error": f"parallel dispatch failed for task {idx}"}

    # Fill any missing results
    for i, r in enumerate(results):
        if r is None:
            results[i] = {"error": f"task {i} did not complete"}
        if isinstance(results[i], dict):
            results[i]["_meta"] = {"tool": tasks[i]["tool"], "duration": round(timings[i], 3)}

    return results


# ---------------------------------------------------------------------------
# 4. Dependency-aware step scheduler for agent.run()
# ---------------------------------------------------------------------------

# Step dependency rules: which skills depend on which
_STEP_DEPENDENCIES: dict[str, list[str]] = {
    "check_uvm_compliance": ["generate_testbench"],
    "run_simulation": ["check_uvm_compliance"],
    "analyze_eda_log": ["run_simulation"],
    "coverage_driven_stimulus": ["run_simulation"],
    "vplan_coverage_traceability": ["run_simulation"],
    "open_waveform": ["run_simulation"],
    "formal_failure_debug": ["run_simulation"],
}

# Steps that can run in parallel with each other
_PARALLEL_SAFE: set[frozenset] = {
    frozenset({"check_uvm_compliance", "analyze_coverage"}),
    frozenset({"open_waveform", "analyze_eda_log"}),
    frozenset({"coverage_driven_stimulus", "formal_failure_debug"}),
}


def _depends_on(step_a: str, step_b: str) -> bool:
    """True if step_a depends on step_b (step_b must complete first)."""
    return step_b in _STEP_DEPENDENCIES.get(step_a, [])


def schedule_steps(steps: list[dict], executor_fn: Callable,
                   max_parallel: int = 3) -> list[dict]:
    """Execute recipe steps with dependency-aware parallel scheduling.

    Args:
        steps: [{"skill": name, "why": reason}, ...] from recipe
        executor_fn: callable(skill_name, args) -> result dict
        max_parallel: max concurrent steps

    Returns:
        Results in the same order as input steps, each enriched with
        "_scheduling" metadata (start/end time, parallel group, skipped reason).
    """
    n = len(steps)
    results: list[dict | None] = [None] * n
    completed: set[str] = set()
    failed: set[str] = set()
    lock = threading.Lock()

    def _can_start(idx: int) -> tuple[bool, str]:
        """Check if step idx can start now (all deps completed, no failed deps)."""
        skill = steps[idx]["skill"]
        deps = _STEP_DEPENDENCIES.get(skill, [])
        for dep in deps:
            if dep in failed:
                return False, f"skipped: dependency '{dep}' failed"
            if dep not in completed:
                return False, f"waiting: dependency '{dep}' not yet complete"
        return True, ""

    def _execute(idx: int) -> tuple[int, dict, float]:
        t0 = time.perf_counter()
        step = steps[idx]
        res = executor_fn(step["skill"], step.get("args", {}))
        return idx, res, time.perf_counter() - t0

    pending = set(range(n))
    round_num = 0
    while pending:
        round_num += 1
        # Find all steps that can start now
        ready = []
        for idx in sorted(pending):
            can, reason = _can_start(idx)
            if not can:
                if reason.startswith("skipped"):
                    results[idx] = {
                        "skipped": True, "reason": reason,
                        "skill": steps[idx]["skill"],
                        "_scheduling": {"round": round_num, "skipped": True},
                    }
                    pending.discard(idx)
                    failed.add(steps[idx]["skill"])
            else:
                ready.append(idx)

        if not ready:
            # All remaining are blocked → break deadlock
            for idx in sorted(pending):
                can, reason = _can_start(idx)
                if not can and reason.startswith("waiting"):
                    results[idx] = {
                        "skipped": True,
                        "reason": f"deadlock: {reason}",
                        "skill": steps[idx]["skill"],
                        "_scheduling": {"round": round_num, "deadlock": True},
                    }
                    pending.discard(idx)
                    failed.add(steps[idx]["skill"])
            if not ready and all(results[i] is not None for i in range(n)):
                break
            if not ready and pending:
                break  # safety valve
            continue

        # Execute ready steps in parallel (bounded)
        batch = ready[:max_parallel]
        with ThreadPoolExecutor(max_workers=min(len(batch), max_parallel)) as pool:
            futures = {pool.submit(_execute, idx): idx for idx in batch}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    _, res, dt = future.result()
                except Exception as e:
                    res = {"error": str(e)}
                    dt = 0.0
                skill = steps[idx]["skill"]
                ok = not (isinstance(res, dict) and "error" in res)
                if isinstance(res, dict):
                    res["_scheduling"] = {
                        "round": round_num, "duration": round(dt, 3), "ok": ok,
                    }
                results[idx] = res
                with lock:
                    if ok:
                        completed.add(skill)
                    else:
                        failed.add(skill)
                    pending.discard(idx)

    # Fill any remaining None results
    for i in range(n):
        if results[i] is None:
            results[i] = {"skipped": True, "reason": "not scheduled",
                          "skill": steps[i]["skill"]}

    return results


# ---------------------------------------------------------------------------
# 5. Warm index preload (background at server startup)
# ---------------------------------------------------------------------------

_warm_threads: list[threading.Thread] = []


def preload_indexes(background: bool = True) -> dict:
    """Preload heavy index files into memory cache for faster first query.

    When ``background=True``, spawns daemon threads and returns immediately.
    """
    loaders = {
        "ug_index": lambda: _warm_ug(),
        "manual_ingest": lambda: _warm_manual(),
        "uvm_semantic": lambda: _warm_uvm_semantic(),
    }
    results = {}
    for name, fn in loaders.items():
        if background:
            th = threading.Thread(target=fn, daemon=True, name=f"warm-{name}")
            th.start()
            _warm_threads.append(th)
            results[name] = "preloading in background"
        else:
            t0 = time.perf_counter()
            try:
                fn()
                results[name] = f"loaded in {time.perf_counter() - t0:.2f}s"
            except Exception as e:
                results[name] = f"error: {e}"
    return results


def _warm_ug():
    try:
        from . import ug_index
        ug_index._load(ug_index._ug_root())
    except Exception:
        pass

def _warm_manual():
    try:
        from . import manual_ingest
        manual_ingest._load_index()
    except Exception:
        pass

def _warm_uvm_semantic():
    try:
        from . import uvm_src_tools
        uvm_src_tools._load_or_build()
    except Exception:
        pass


def scheduler_status() -> dict:
    """Full scheduler health report."""
    return {
        "cache": cache_stats(),
        "circuit_breaker": cb_stats(),
        "warm_threads_alive": sum(1 for t in _warm_threads if t.is_alive()),
        "dependencies": _STEP_DEPENDENCIES,
        "parallel_safe_groups": [sorted(s) for s in _PARALLEL_SAFE],
    }
