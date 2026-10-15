"""Lightweight in-process counters for tool-call observability.

Both protocol paths (legacy call_tool and SDK _sdk_call) funnel every
tool invocation through record(), so the snapshot covers dual-mode traffic.
Counters are process-local by design (no external deps, no I/O on the hot
path); expose them via the chip://metrics resource.
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_STARTED = time.time()
_PER_TOOL: dict[str, dict] = {}
_CACHE_HITS = 0


def record(name: str, duration_ms: float, error: bool) -> None:
    with _LOCK:
        m = _PER_TOOL.setdefault(
            name, {"calls": 0, "errors": 0, "total_ms": 0.0})
        m["calls"] += 1
        m["total_ms"] += duration_ms
        if error:
            m["errors"] += 1


def record_cache_hit() -> None:
    global _CACHE_HITS
    with _LOCK:
        _CACHE_HITS += 1


def snapshot() -> dict:
    with _LOCK:
        tools = {
            name: {
                **m,
                "avg_ms": round(m["total_ms"] / m["calls"], 2),
                "error_rate": round(m["errors"] / m["calls"], 3),
            }
            for name, m in sorted(_PER_TOOL.items())
        }
        return {
            "uptime_s": round(time.time() - _STARTED, 1),
            "tool_calls": sum(m["calls"] for m in _PER_TOOL.values()),
            "tool_errors": sum(m["errors"] for m in _PER_TOOL.values()),
            "sdk_cache_hits": _CACHE_HITS,
            "tools": tools,
        }


def reset() -> None:
    """Test hook: zero all counters (server code never calls this)."""
    global _CACHE_HITS
    with _LOCK:
        _PER_TOOL.clear()
        _CACHE_HITS = 0
