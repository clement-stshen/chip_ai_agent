"""Code-enforced fix_request closed loop (digital-chip-design-agents protocol).

Python implementation of the pipeline-orchestration protocol vendored from
digital-chip-design-agents (plugins/meta). The markdown orchestrators define
the contract; this module enforces it deterministically:

  verification/formal orchestrator  -> open_fix_request()  (status=open)
  rtl orchestrator                  -> claim()/close_fix_request()
  pipeline driver                   -> next_pipeline_action():
       - pending_approval gate -> hold
       - concurrency guard     -> hold (claimed within 10 min)
       - iteration cap         -> escalate
       - divergence check      -> escalate (same module+summary recurred
                                   within one pipeline session)
       - otherwise             -> dispatch RTL -> re-verify -> archive on signoff

State file (design_state.json) follows docs/design_state.schema.json
(vendored at digital/docs/design_state.schema.json).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_STATE_PATH = os.environ.get(
    "CHIP_DESIGN_STATE", str(Path(__file__).parent / "design_state.json"))

FIX_STATUSES = ("open", "claimed", "fixed", "abandoned")
CREATORS = ("verification-orchestrator", "formal-orchestrator", "chip_agent")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class DesignStateError(ValueError):
    """Protocol violation (invalid transition, malformed entry...)."""


class DesignState:
    def __init__(self, path: str | Path = DEFAULT_STATE_PATH):
        self.path = Path(path)
        self.data: dict = self._load()

    # -- persistence ---------------------------------------------------------
    def _load(self) -> dict:
        if not self.path.exists():
            return {"format_version": "1.5", "design_name": None,
                    "created_at": _now(), "updated_at": _now(),
                    "pipeline_session_id": None,
                    "cross_domain_iteration_count": 0,
                    "pipeline_config": {"max_cross_domain_iterations": 3},
                    "pending_approval": None, "fix_requests": [],
                    "archive_fix_requests": [], "history": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("format_version") not in ("1.1", "1.2", "1.3", "1.4", "1.5"):
            raise DesignStateError(
                f"unsupported format_version: {data.get('format_version')!r}")
        data.setdefault("fix_requests", [])
        data.setdefault("archive_fix_requests", [])
        data.setdefault("history", [])
        data.setdefault("pending_approval", None)
        data.setdefault("cross_domain_iteration_count", 0)
        data.setdefault("pipeline_config", {})
        data["pipeline_config"].setdefault("max_cross_domain_iterations", 3)
        return data

    def save(self) -> None:
        """Atomic write: never leave a half-written design_state.json."""
        self.data["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent,
                                   prefix=".design_state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- fix_request lifecycle ------------------------------------------------
    def open_fix_request(self, *, created_by: str, failure_class: str,
                         summary: str, test_name: str = "",
                         module: str = "", signal: str | None = None,
                         file: str | None = None,
                         expected: str | None = None,
                         observed: str | None = None,
                         waveform_path: str | None = None,
                         log_path: str | None = None) -> dict:
        if created_by not in CREATORS:
            raise DesignStateError(f"created_by must be one of {CREATORS}")
        if failure_class not in ("functional", "protocol", "coverage_gap",
                                 "formal_cex"):
            raise DesignStateError(
                "failure_class must be functional|protocol|coverage_gap|formal_cex")
        if not summary or not summary.strip():
            raise DesignStateError("summary is required")
        now = _now()
        seq = len(self.data["fix_requests"]) + \
            len(self.data["archive_fix_requests"]) + 1
        sid = self.data.get("pipeline_session_id") or \
            f"ps_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fr = {
            "id": f"fr_{sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{seq}",
            "created_at": now, "updated_at": now,
            "created_by": created_by, "failure_class": failure_class,
            "retry_strategy": "refine",
            "test_name": test_name, "property_or_assertion": None,
            "seed": 0, "waveform_path": waveform_path, "log_path": log_path,
            "suspected_rtl": {"module": module, "signal": signal,
                              "file": file, "line_range": [0, 0]},
            "summary": summary.strip(),
            "expected_behavior": expected, "observed_behavior": observed,
            "session_id": sid, "status": "open", "rtl_response": None,
            "history": [{"timestamp": now, "agent": created_by,
                         "from_status": None, "to_status": "open",
                         "note": "bug detected"}],
        }
        self.data["fix_requests"].append(fr)
        self._history("fix_request_open", fix_request_id=fr["id"],
                      note=summary.strip())
        return fr

    def _find(self, fr_id: str) -> tuple[int, dict]:
        for i, fr in enumerate(self.data["fix_requests"]):
            if fr["id"] == fr_id:
                return i, fr
        raise DesignStateError(f"fix_request not found: {fr_id}")

    def claim(self, fr_id: str, agent: str = "rtl-design-orchestrator") -> dict:
        _, fr = self._find(fr_id)
        if fr["status"] != "open":
            raise DesignStateError(
                f"claim requires status=open, got {fr['status']}")
        self._transition(fr, agent, "claimed", "claimed by RTL")
        return fr

    def close_fix_request(self, fr_id: str, *, fixed: bool,
                          diff_summary: str = "", files_changed: list[str] | None = None,
                          agent: str = "rtl-design-orchestrator") -> dict:
        _, fr = self._find(fr_id)
        if fr["status"] != "claimed":
            raise DesignStateError(
                f"close requires status=claimed, got {fr['status']}")
        new = "fixed" if fixed else "abandoned"
        self._transition(fr, agent, new,
                         "RTL fix applied" if fixed else "RTL gave up")
        if fixed:
            fr["rtl_response"] = {
                "fixed_at": _now(), "diff_summary": diff_summary,
                "files_changed": files_changed or [], "commit_ref": None}
        return fr

    def _transition(self, fr: dict, agent: str, to_status: str, note: str) -> None:
        now = _now()
        fr["history"].append({"timestamp": now, "agent": agent,
                              "from_status": fr["status"],
                              "to_status": to_status, "note": note})
        fr["status"] = to_status
        fr["updated_at"] = now

    # -- pipeline driver -----------------------------------------------------
    def next_pipeline_action(self) -> dict:
        """Decide the next deterministic step of the closed loop."""
        pa = self.data.get("pending_approval")
        if pa:
            return {"action": "hold", "reason": "pending_approval is set",
                    "pending_approval": pa,
                    "unblock": "clear pending_approval (set null) to resume"}
        now = datetime.now(timezone.utc)
        # concurrency guard: claimed within the last 10 minutes
        for fr in self.data["fix_requests"]:
            if fr["status"] == "claimed":
                ts = _parse_ts(fr.get("updated_at", ""))
                if ts and now - ts < timedelta(minutes=10):
                    return {"action": "hold",
                            "reason": "another pipeline run holds a claimed "
                                      "fix_request (updated <10min ago)",
                            "fix_request_id": fr["id"]}
        opens = [fr for fr in self.data["fix_requests"] if fr["status"] == "open"]
        if not opens:
            done = [fr for fr in self.data["fix_requests"]
                    if fr["status"] in ("fixed", "abandoned")]
            if done:
                return {"action": "signoff", "reason":
                        "no open fix_requests; resolved entries can be archived",
                        "resolved_ids": [fr["id"] for fr in done]}
            return {"action": "idle", "reason": "no fix_requests"}
        fr = sorted(opens, key=lambda f: (f.get("created_at", ""), f["id"]))[0]

        cap = int(self.data["pipeline_config"].get(
            "max_cross_domain_iterations", 3))
        count = int(self.data.get("cross_domain_iteration_count", 0))
        if count >= cap:
            self._escalate(f"iteration cap {cap}x exhausted with open fix_request {fr['id']}")
            return {"action": "escalate", "reason": f"iteration cap {cap}x exhausted",
                    "fix_request_id": fr["id"], "iteration_count": count}

        # divergence: same module+summary already fixed within this session
        sid = self.data.get("pipeline_session_id")
        for done in (self.data["fix_requests"]
                     + self.data.get("archive_fix_requests", [])):
            if (done["status"] == "fixed" and done.get("session_id") == sid
                    and done["suspected_rtl"].get("module") == fr["suspected_rtl"].get("module")
                    and done["summary"] == fr["summary"]):
                self._escalate(
                    f"divergence: fix_request {fr['id']} repeats previously "
                    f"fixed failure {done['id']} in session {sid}")
                return {"action": "escalate",
                        "reason": "same failure recurred after prior fix "
                                  "(divergence detected)",
                        "fix_request_id": fr["id"],
                        "prior_fixed_id": done["id"]}

        self.data["cross_domain_iteration_count"] = count + 1
        return {"action": "dispatch_rtl", "fix_request_id": fr["id"],
                "summary": fr["summary"], "module": fr["suspected_rtl"].get("module"),
                "iteration_count": count + 1, "cap": cap,
                "next": "rtl fix -> re_verify (created_by decides verifier)"}

    def _escalate(self, reason: str) -> None:
        self.data["pending_approval"] = {"type": "escalation", "reason": reason,
                                         "agent": "pipeline-orchestrator",
                                         "set_at": _now()}
        self._history("escalate", note=reason)

    def archive_resolved(self) -> list[str]:
        """Move fixed/abandoned entries to archive_fix_requests (signoff path)."""
        keep, archived = [], []
        for fr in self.data["fix_requests"]:
            if fr["status"] in ("fixed", "abandoned"):
                self.data["archive_fix_requests"].append(fr)
                archived.append(fr["id"])
            else:
                keep.append(fr)
        self.data["fix_requests"] = keep
        if archived:
            self._history("archive", note=f"archived {len(archived)} resolved entries")
        return archived

    def ensure_session(self) -> str:
        sid = self.data.get("pipeline_session_id")
        if not sid:
            sid = f"ps_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.data["pipeline_session_id"] = sid
        # adopt orphaned open entries into this session
        for fr in self.data["fix_requests"]:
            if fr["status"] == "open" and not fr.get("session_id"):
                fr["session_id"] = sid
        return sid

    def _history(self, decision: str, **kw) -> None:
        self.data["history"].append(
            {"timestamp": _now(), "agent": "pipeline-orchestrator",
             "decision": decision, **kw})

    # -- reporting -------------------------------------------------------------
    def summary(self) -> dict:
        by = {}
        for fr in self.data["fix_requests"]:
            by[fr["status"]] = by.get(fr["status"], 0) + 1
        return {
            "state_path": str(self.path),
            "design_name": self.data.get("design_name"),
            "pipeline_session_id": self.data.get("pipeline_session_id"),
            "cross_domain_iteration_count": self.data.get(
                "cross_domain_iteration_count", 0),
            "max_cross_domain_iterations": self.data["pipeline_config"].get(
                "max_cross_domain_iterations", 3),
            "pending_approval": self.data.get("pending_approval"),
            "fix_requests_by_status": by,
            "open_fix_requests": [
                {"id": fr["id"], "summary": fr["summary"],
                 "module": fr["suspected_rtl"].get("module"),
                 "failure_class": fr["failure_class"]}
                for fr in self.data["fix_requests"] if fr["status"] == "open"],
        }
