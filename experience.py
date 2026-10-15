"""JSONL experience memory with TF-IDF keyword retrieval, inspired by
digital-chip-design-agents tools/experience_search.py (stdlib-only backend).

Proactive-memory extensions (Phase 1):
  - every record gets a timestamp; retrieval applies recency decay so old
    cases no longer outrank yesterday's fixes;
  - records may carry an environment fingerprint (EDA tool set / UVM kit /
    python); records from a different environment are down-weighted;
  - status filtering (`successes()`) powers success-path replay in planning.
"""

from __future__ import annotations

import json
import math
import re
import time
import threading
from pathlib import Path

# records older than one half-life score half as much
DEFAULT_DECAY_HALF_LIFE_DAYS = 30.0
# records from a different environment fingerprint are down-weighted
ENV_MISMATCH_PENALTY = 0.5


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


class ExperienceStore:
    FIELDS = ("intent", "recipe", "failure_class", "reason")

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # add_if_new does read-modify-write (dedup against the last line,
        # then atomic whole-file rewrite); guard it independently so it is
        # safe even when callers no longer hold the agent's op lock.
        # RLock: add_if_new holds the lock across its dedup check and then
        # falls through to self.add(), which re-acquires it.
        self._lock = threading.RLock()

    def add(self, record: dict, env_fp: str | None = None) -> dict:
        rec = dict(record)
        rec.setdefault("free_text", " ".join(str(rec.get(f, "")) for f in self.FIELDS))
        rec["free_text"] += " " + " ".join(
            str(v) for v in rec.get("failed_skills", []) if isinstance(v, str))
        rec.setdefault("ts", time.time())
        if env_fp:
            rec.setdefault("env_fp", env_fp)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def add_if_new(self, record: dict, env_fp: str | None = None) -> dict:
        """Deduplicate consecutive retries: skip the append when the record
        duplicates the LAST line on (intent, recipe, failure_class, status).
        Fast path reads one line only; on a hit the counter is persisted by
        an atomic last-line rewrite (small files, callers hold the op lock).
        """
        rec = dict(record)
        rec.setdefault("ts", time.time())
        if env_fp:
            rec.setdefault("env_fp", env_fp)
        with self._lock:
            try:
                text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
                lines = [ln for ln in text.splitlines() if ln.strip()]
                if lines:
                    last = json.loads(lines[-1])
                    keys = ("intent", "recipe", "failure_class", "status")
                    if all(last.get(k) == rec.get(k) for k in keys):
                        last["repeat_count"] = last.get("repeat_count", 1) + 1
                        last["last_ts"] = rec["ts"]
                        lines[-1] = json.dumps(last, ensure_ascii=False)
                        tmp = self.path.with_suffix(".jsonl.tmp")
                        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
                        tmp.replace(self.path)
                        return last
            except (OSError, json.JSONDecodeError):
                pass
            return self.add(rec, env_fp=env_fp)

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
        return out

    def search(self, query: str, limit: int = 3, *,
               env_fp: str | None = None,
               decay_half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS,
               status: str | None = None) -> list[dict]:
        """TF-IDF cosine ranking with recency decay and environment matching.

        - score *= exp(-ln2 * age_days / half_life): recent cases rank higher;
          records without a timestamp are treated as recent (no decay).
        - score *= ENV_MISMATCH_PENALTY when the record carries a different
          env_fp (missing fingerprints are neutral — legacy records).
        - status filters records (e.g. "success" for success-path replay).
        """
        recs = self.records()
        if status:
            recs = [r for r in recs if r.get("status") == status]
        if not recs:
            return []
        q = _tokens(query)
        if not q:
            return []
        docs = [_tokens(r.get("free_text", "")) for r in recs]
        n = len(recs)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1

        def idf(t: str) -> float:
            return math.log(n / df[t]) + 1.0 if t in df else 0.0

        def tf(tokens: list[str]) -> dict[str, float]:
            tfd: dict[str, float] = {}
            for t in tokens:
                tfd[t] = tfd.get(t, 0) + 1.0
            return tfd

        now = time.time()
        half = max(decay_half_life_days, 1.0) * 86400.0
        qv = {t: c * idf(t) for t, c in tf(q).items()}
        qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
        scored = []
        for rec, d in zip(recs, docs):
            dv = {t: c * idf(t) for t, c in tf(d).items() if t in qv}
            dn = math.sqrt(sum(v * v for v in dv.values())) or 1.0
            score = sum(qv[t] * dv[t] for t in dv) / (qn * dn)
            if score <= 0:
                continue
            ts = rec.get("ts")
            if isinstance(ts, (int, float)):
                age_days = max(now - float(ts), 0.0) / 86400.0
                score *= math.exp(-math.log(2) * age_days / max(decay_half_life_days, 1.0))
            rec_fp = rec.get("env_fp")
            if env_fp and rec_fp and rec_fp != env_fp:
                score *= ENV_MISMATCH_PENALTY
            scored.append({"score": round(score, 4), "record": rec})
        scored.sort(key=lambda x: -x["score"])
        return scored[:limit]

    def successes(self, query: str, limit: int = 1, **kw) -> list[dict]:
        """Last successful runs similar to `query` (success-path replay)."""
        return self.search(query, limit=limit, status="success", **kw)
