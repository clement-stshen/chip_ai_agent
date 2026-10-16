#!/usr/bin/env python3
"""Data quality audit & cleaning for chip-ai-agent data stores.

Dirty-data categories handled:
  experience (experiences.jsonl):
    - info-free records: status=empty / step_count=0 (no debugging value)
    - degraded runs: all steps ERR due to missing MCP server (environment
      noise, not real failure knowledge)  -> flagged, removable
    - duplicates: same (intent, recipe, failure_class, failed_skills)
    - malformed lines: invalid JSON, missing required fields
  runs DB (SQLite):
    - empty runs (0 steps), orphan steps, stale empty DBs
  skills:
    - unparseable blobs, SKILL.md without name
  filesystem:
    - stale generated testbench dirs in /tmp

Cleaning is always backup-first (.bak alongside), never destructive.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

REQUIRED_FIELDS = ("intent", "recipe", "status", "failure_class")


def _load_jsonl(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


def audit_experience(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": path, "exists": False}
    raw = p.read_text(encoding="utf-8").splitlines()
    recs, bad_lines = [], 0
    for ln in raw:
        if not ln.strip():
            continue
        try:
            recs.append(json.loads(ln))
        except json.JSONDecodeError:
            bad_lines += 1
    info_free = [r for r in recs
                 if r.get("status") == "empty" or r.get("step_count", 0) == 0]
    degraded = [r for r in recs
                if r.get("status") == "partial"
                and str(r.get("reason", "")).startswith("LLM planner unavailable")]
    seen, dupes = set(), []
    for r in recs:
        key = (r.get("intent"), r.get("recipe"), r.get("failure_class"),
               tuple(r.get("failed_skills", [])))
        if key in seen:
            dupes.append(r)
        seen.add(key)
    missing = [r for r in recs if any(f not in r for f in REQUIRED_FIELDS)]
    return {"path": path, "exists": True, "total": len(recs),
            "issues": {"info_free": len(info_free), "degraded_llm_fallback": len(degraded),
                       "duplicates": len(dupes), "malformed_lines": bad_lines,
                       "missing_fields": len(missing)}}


def clean_experience(path: str, keep_degraded: bool = False) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": path, "removed": 0, "kept": 0}
    recs = _load_jsonl(p)
    # backup first
    bak = p.with_suffix(p.suffix + f".bak.{int(time.time())}")
    shutil.copy2(p, bak)
    seen, kept = set(), []
    for r in recs:
        if any(f not in r for f in REQUIRED_FIELDS):
            continue                                   # malformed
        if r.get("status") == "empty" or r.get("step_count", 0) == 0:
            continue                                   # info-free
        if not keep_degraded and str(r.get("reason", "")).startswith(
                "LLM planner unavailable"):
            continue                                   # env noise
        key = (r.get("intent"), r.get("recipe"), r.get("failure_class"),
               tuple(r.get("failed_skills", [])))
        if key in seen:
            continue                                   # duplicate
        seen.add(key)
        kept.append(r)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in kept) +
                ("\n" if kept else ""), encoding="utf-8")
    return {"path": str(p), "backup": str(bak), "removed": len(recs) - len(kept),
            "kept": len(kept)}


def audit_db(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": path, "exists": False}
    c = sqlite3.connect(p)
    try:
        runs = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        steps = c.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
        empty = c.execute(
            "SELECT COUNT(*) FROM runs WHERE id NOT IN (SELECT run_id FROM steps)"
        ).fetchone()[0]
        orphans = c.execute(
            "SELECT COUNT(*) FROM steps WHERE run_id NOT IN (SELECT id FROM runs)"
        ).fetchone()[0] if steps else 0
        return {"path": path, "exists": True, "runs": runs, "steps": steps,
                "issues": {"empty_runs": empty, "orphan_steps": orphans,
                           "stale_empty_db": runs == 0}}
    except sqlite3.DatabaseError as e:
        return {"path": path, "exists": True, "error": str(e)}
    finally:
        c.close()


def clean_db(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": path, "removed_runs": 0}
    bak = p.with_name(p.name + f".bak.{int(time.time())}")
    shutil.copy2(p, bak)
    c = sqlite3.connect(p)
    try:
        cur = c.execute(
            "DELETE FROM runs WHERE id NOT IN (SELECT run_id FROM steps)")
        removed = cur.rowcount
        c.execute("DELETE FROM steps WHERE run_id NOT IN (SELECT id FROM runs)")
        c.commit()
        return {"path": str(p), "backup": str(bak), "removed_runs": removed}
    finally:
        c.close()


def audit_stale_generated(max_age_hours: float = 24.0) -> dict:
    import tempfile
    stale = []
    for d in Path(tempfile.gettempdir()).glob("uvm_tb_gen_*"):
        try:
            age_h = (time.time() - d.stat().st_mtime) / 3600
        except OSError:
            continue
        if age_h > max_age_hours:
            stale.append({"path": str(d), "age_hours": round(age_h, 1)})
    return {"stale_generated_dirs": stale}


def main() -> int:
    ap = argparse.ArgumentParser(prog="chip-agent-data-quality")
    ap.add_argument("--experience", help="experiences.jsonl path")
    ap.add_argument("--db", help="runs SQLite path")
    ap.add_argument("--clean", action="store_true", help="clean (backup-first) instead of audit only")
    ap.add_argument("--keep-degraded", action="store_true",
                    help="keep LLM-fallback degraded records when cleaning")
    ap.add_argument("--prune-stale-dirs", action="store_true",
                    help="delete generated testbench dirs older than 24h (after listing)")
    args = ap.parse_args()

    rc = 0
    if args.experience:
        if args.clean:
            print("CLEAN experience:", json.dumps(clean_experience(
                args.experience, keep_degraded=args.keep_degraded), ensure_ascii=False))
        else:
            r = audit_experience(args.experience)
            print("AUDIT experience:", json.dumps(r, ensure_ascii=False))
            if r.get("issues") and any(r["issues"].values()):
                rc = 1
    if args.db:
        if args.clean:
            print("CLEAN db:", json.dumps(clean_db(args.db), ensure_ascii=False))
        else:
            r = audit_db(args.db)
            print("AUDIT db:", json.dumps(r, ensure_ascii=False))
            if r.get("issues") and any(r["issues"].values()):
                rc = 1
    stale = audit_stale_generated()
    if stale["stale_generated_dirs"]:
        print("STALE generated dirs:", json.dumps(stale, ensure_ascii=False))
        if args.prune_stale_dirs:
            import shutil as sh
            for d in stale["stale_generated_dirs"]:
                sh.rmtree(d["path"], ignore_errors=True)
            print(f"pruned {len(stale['stale_generated_dirs'])} stale dir(s)")
    if not (args.experience or args.db):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
