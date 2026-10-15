"""SQLite-backed RunReport store: turn every debug run into reusable knowledge.

Proactive-learning extensions:
  - steps carry structured failure_class and duration (schema migration on
    open, backward compatible);
  - successful-run lookup powers success-path replay in planning;
  - success rates accept a minimum-sample floor so one failure cannot
    masquerade as a 0% skill;
  - the skill x failure_class matrix feeds risk annotation in plans.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from typing import TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from .agent import RunReport


class ReportStore:
    def __init__(self, db_path: str | Path = "chip_agent_runs.db"):
        # one long-lived connection, guarded by a lock: the MCP server may
        # dispatch concurrent tool calls from different worker threads.
        # check_same_thread=False allows the (lock-serialized) connection to
        # be touched from any thread; WAL + busy_timeout keep other processes
        # tolerant of concurrent readers/writers.
        self.path = Path(db_path)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, intent TEXT, recipe TEXT, title TEXT
            );
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER REFERENCES runs(id),
                seq INTEGER, skill TEXT, why TEXT, ok INTEGER, detail TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_steps_skill ON steps(skill);
            CREATE INDEX IF NOT EXISTS idx_runs_recipe ON runs(recipe);
            """
        )
        self._migrate_steps()
        self.conn.commit()

    def _migrate_steps(self) -> None:
        """Add structured learning columns to pre-existing databases."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(steps)")}
        if "failure_class" not in cols:
            self.conn.execute("ALTER TABLE steps ADD COLUMN failure_class TEXT")
        if "duration" not in cols:
            self.conn.execute("ALTER TABLE steps ADD COLUMN duration REAL")
        if "retry_strategy" not in cols:
            self.conn.execute("ALTER TABLE steps ADD COLUMN retry_strategy TEXT")

    def save(self, report: "RunReport") -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO runs(ts, intent, recipe, title) VALUES (?,?,?,?)",
                (time.time(), report.intent, report.recipe, report.title),
            )
            run_id = cur.lastrowid
            for i, s in enumerate(report.steps, 1):
                self.conn.execute(
                    "INSERT INTO steps(run_id, seq, skill, why, ok, detail,"
                    " failure_class, duration, retry_strategy)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (run_id, i, s.skill, s.why, int(s.ok), s.detail,
                     getattr(s, "failure_class", None),
                     getattr(s, "duration", None),
                     getattr(s, "retry_strategy", None)),
                )
            self.conn.commit()
        return run_id

    def history(self, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, ts, intent, recipe, title FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "ts": r[1], "intent": r[2], "recipe": r[3], "title": r[4]}
            for r in rows
        ]

    def runs_using_skill(self, skill: str, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT DISTINCT r.id, r.intent, r.recipe FROM runs r
                JOIN steps s ON s.run_id = r.id
                WHERE s.skill = ? ORDER BY r.id DESC LIMIT ?
                """,
                (skill, limit),
            ).fetchall()
        return [{"id": r[0], "intent": r[1], "recipe": r[2]} for r in rows]

    def skill_success_rate(self, min_samples: int = 1,
                           ) -> list[tuple[str, int, int]]:
        """(skill, count, ok) ordered by count desc; skills below the sample
        floor are dropped so single failures cannot masquerade as 0%."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT skill, COUNT(*), SUM(ok) FROM steps"
                " GROUP BY skill HAVING COUNT(*) >= ?"
                " ORDER BY COUNT(*) DESC",
                (min_samples,),
            ).fetchall()
        return [(r[0], r[1], int(r[2] or 0)) for r in rows]

    def successful_runs(self, recipe: str, limit: int = 1) -> list[dict]:
        """Runs of `recipe` where every step passed (success-path replay)."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT r.id, r.intent, r.recipe, r.ts FROM runs r
                WHERE r.recipe = ?
                  AND EXISTS (SELECT 1 FROM steps s WHERE s.run_id = r.id)
                  AND NOT EXISTS (SELECT 1 FROM steps s
                                  WHERE s.run_id = r.id AND s.ok = 0)
                ORDER BY r.id DESC LIMIT ?
                """,
                (recipe, limit),
            ).fetchall()
        return [{"id": r[0], "intent": r[1], "recipe": r[2], "ts": r[3]}
                for r in rows]

    def run_steps(self, run_id: int) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT seq, skill, why, ok, failure_class, duration,"
                " retry_strategy FROM steps WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        return [{"seq": r[0], "skill": r[1], "why": r[2], "ok": bool(r[3]),
                 "failure_class": r[4], "duration": r[5],
                 "retry_strategy": r[6]} for r in rows]

    def run_count(self) -> int:
        with self._lock:
            return self.conn.execute(
                "SELECT COUNT(*) FROM runs").fetchone()[0]

    def attempt_number(self, intent: str, recipe: str) -> int:
        """Trial-trajectory tracking: how many CONSECUTIVE runs of the same
        intent+recipe precede this one (the next run is attempt N+1)."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT intent FROM runs WHERE recipe = ?"
                " ORDER BY id DESC LIMIT 20",
                (recipe,),
            ).fetchall()
        n = 0
        for (i,) in rows:
            if i == intent:
                n += 1
            else:
                break
        return n + 1

    def last_run(self, intent: str) -> dict | None:
        """Most recent run with this intent + its failed skills — the basis
        for trial-trajectory comparison ("what changed since last attempt")."""
        with self._lock:
            row = self.conn.execute(
                "SELECT id, recipe, ts FROM runs WHERE intent = ?"
                " ORDER BY id DESC LIMIT 1",
                (intent,),
            ).fetchone()
        if not row:
            return None
        with self._lock:
            fails = [r[0] for r in self.conn.execute(
                "SELECT DISTINCT skill FROM steps WHERE run_id = ? AND ok = 0",
                (row[0],)).fetchall()]
        return {"run_id": row[0], "recipe": row[1], "ts": row[2],
                "failed_skills": fails}

    def recipe_runs(self, recipe: str, limit: int = 5) -> list[dict]:
        """Recent runs of a recipe with per-run outcome (merged-retrieval
        tier 3: the full trajectory DB, coarser than experiences)."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT r.id, r.intent, r.ts,
                       (SELECT COUNT(*) FROM steps s WHERE s.run_id = r.id),
                       (SELECT COUNT(*) FROM steps s
                        WHERE s.run_id = r.id AND s.ok = 0)
                FROM runs r WHERE r.recipe = ? ORDER BY r.id DESC LIMIT ?
                """,
                (recipe, limit),
            ).fetchall()
        return [{"run_id": r[0], "intent": r[1], "ts": r[2],
                 "step_count": r[3], "failed_steps": r[4],
                 "status": "success" if r[4] == 0 else "partial"}
                for r in rows]

    def recipe_success_trend(self, recipe: str, window: int = 5,
                             ) -> dict | None:
        """Recent-vs-earlier success rate for a recipe; a drop in the recent
        window is a regression signal (QoR-style guard, DB-only)."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT r.id,
                       EXISTS(SELECT 1 FROM steps s
                              WHERE s.run_id = r.id AND s.ok = 0) AS failed
                FROM runs r WHERE r.recipe = ? ORDER BY r.id DESC
                LIMIT ?
                """,
                (recipe, window * 2),
            ).fetchall()
        if len(rows) < max(window, 3):
            return None
        recent = rows[:window]
        older = rows[window:]
        if not older:
            return None

        def rate(part):
            return 1.0 - sum(1 for _, f in part if f) / len(part)
        recent_rate, older_rate = rate(recent), rate(older)
        return {"recent_rate": round(recent_rate, 2),
                "older_rate": round(older_rate, 2),
                "recent_runs": len(recent), "older_runs": len(older),
                "regression": recent_rate < older_rate - 0.2}

    def skill_failure_stats(self, min_samples: int = 3,
                            ) -> dict[str, list[tuple[str, int]]]:
        """skill -> [(failure_class, count)] — which failures recur per skill."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT skill, failure_class, COUNT(*) FROM steps
                WHERE ok = 0 AND failure_class IS NOT NULL
                GROUP BY skill, failure_class
                ORDER BY COUNT(*) DESC
                """,
            ).fetchall()
        by_skill: dict[str, list[tuple[str, int]]] = {}
        for skill, fc, cnt in rows:
            by_skill.setdefault(skill, []).append((fc, cnt))
        for skill in list(by_skill):
            total = sum(c for _, c in by_skill[skill])
            if total < min_samples:
                del by_skill[skill]
        return by_skill

    def skill_failure_strategies(self, min_samples: int = 2,
                                 ) -> dict[str, list[tuple[str, int, str]]]:
        """skill -> [(failure_class, count, retry_strategy)] — the recurring
        failure classes WITH the strategy that fixed them historically."""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT skill, failure_class, retry_strategy, COUNT(*)
                FROM steps
                WHERE ok = 0 AND failure_class IS NOT NULL
                GROUP BY skill, failure_class, retry_strategy
                ORDER BY COUNT(*) DESC
                """,
            ).fetchall()
        by_skill: dict[str, list[tuple[str, int, str]]] = {}
        for skill, fc, strat, cnt in rows:
            by_skill.setdefault(skill, []).append(
                (fc, cnt, strat or "unknown"))
        for skill in list(by_skill):
            total = sum(c for _, c, _ in by_skill[skill])
            if total < min_samples:
                del by_skill[skill]
        return by_skill

    def close(self):
        with self._lock:
            self.conn.close()
