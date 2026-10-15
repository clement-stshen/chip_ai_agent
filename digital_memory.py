"""Two-tier persistent memory (digital-chip-design-agents memory system).

Tier 1: <domain>/experiences.jsonl — one record per orchestrator run,
        upserted by run_id, written on every termination path.
Tier 2: <domain>/knowledge.md    — distilled knowledge, seeded from the
        vendored upstream tree, grown by distill.py / memory-keeper.

Root resolution (same priority order as upstream memory_root.py):
  1. explicit --memory-root / constructor arg
  2. $CHIP_DESIGN_MEMORY_ROOT
  3. ${XDG_DATA_HOME:-~/.local/share}/chip-design-agents/digital/memory
  4. vendored seed tree (read-only fallback)
Seeding copies knowledge.md only when absent — accumulated runtime data
is never overwritten.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parent / "digital"
VALID_DOMAINS = [
    "architecture", "compiler", "dft", "firmware", "formal", "fpga",
    "hls", "infrastructure", "memory-ip", "meta", "pd", "rtl-design",
    "soc", "sta", "synthesis", "verification",
]


def resolve_memory_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("CHIP_DESIGN_MEMORY_ROOT")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_DATA_HOME") or str(
        Path.home() / ".local" / "share")
    central = Path(xdg) / "chip-design-agents" / "digital" / "memory"
    try:
        central.mkdir(parents=True, exist_ok=True)
        _seed(central)
        return central
    except OSError:
        return VENDOR_ROOT / "memory"          # read-only seed fallback


def _seed(root: Path) -> None:
    """Copy vendored knowledge.md into root/<domain>/ if absent."""
    src_root = VENDOR_ROOT / "memory"
    for d in VALID_DOMAINS:
        src = src_root / d / "knowledge.md"
        dst = root / d / "knowledge.md"
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


class DomainMemory:
    def __init__(self, domain: str, root: str | Path | None = None):
        if domain not in VALID_DOMAINS:
            raise ValueError(f"unknown domain: {domain!r} "
                             f"(valid: {', '.join(VALID_DOMAINS)})")
        self.domain = domain
        self.root = resolve_memory_root(root)
        self.dir = self.root / domain
        self.dir.mkdir(parents=True, exist_ok=True)
        _seed(self.root)   # idempotent: only fills absent knowledge.md files

    # -- tier 2: knowledge ------------------------------------------------------
    def knowledge(self) -> str:
        p = self.dir / "knowledge.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # -- tier 1: experiences ----------------------------------------------------
    @property
    def jsonl(self) -> Path:
        return self.dir / "experiences.jsonl"

    def records(self) -> list[dict]:
        if not self.jsonl.exists():
            return []
        out = []
        for ln in self.jsonl.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
        return out

    # -- tier 1b: effective step variants (agent learning output) --------------
    @property
    def plans_jsonl(self) -> Path:
        return self.dir / "successful_plans.jsonl"

    def plan_variants(self, recipe: str | None = None,
                      limit: int = 5) -> list[dict]:
        """Effective (successful) skill chains recorded by the agent,
        optionally filtered by recipe key."""
        if not self.plans_jsonl.exists():
            return []
        out = []
        for ln in self.plans_jsonl.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if recipe and r.get("recipe") != recipe:
                continue
            out.append(r)
        out.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return out[:limit]

    def record_plan_variant(self, recipe: str, skills: list[str],
                            intent: str, run_id: int | None) -> dict:
        """Persist a proven-good skill chain (upsert by (recipe, skills)
        keeps the newest ts) — the planner replays these variants."""
        key = json.dumps(skills, ensure_ascii=False)
        all_recs = self.plan_variants()
        old = next((r for r in all_recs
                    if json.dumps(r.get("skills", []),
                                  ensure_ascii=False) == key), None)
        recs = [r for r in all_recs
                if json.dumps(r.get("skills", []), ensure_ascii=False) != key]
        rec = {"recipe": recipe, "skills": skills, "intent": intent,
               "run_id": run_id, "ts": time.time(),
               "successes": (old.get("successes", 0) if old else 0) + 1}
        recs.append(rec)
        tmp = self.plans_jsonl.with_suffix(".tmp")
        tmp.write_text("\n".join(
            json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
            encoding="utf-8")
        tmp.replace(self.plans_jsonl)
        return rec

    def upsert(self, record: dict) -> dict:
        """Insert or replace by run_id (upstream contract)."""
        if not record.get("run_id"):
            raise ValueError("experience record requires run_id")
        record.setdefault("domain", self.domain)
        record.setdefault("signoff_achieved", False)
        recs = [r for r in self.records() if r.get("run_id") != record["run_id"]]
        recs.append(record)
        tmp = self.jsonl.with_suffix(".tmp")
        tmp.write_text("\n".join(
            json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
            encoding="utf-8")
        tmp.replace(self.jsonl)
        return record

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """TF-IDF cosine ranking over the upstream free-text fields."""
        recs = self.records()
        if not recs:
            return []
        q = _tokens(query)
        if not q:
            return []

        def free_text(r: dict) -> str:
            return " ".join(str(x) for x in [
                r.get("run_id"), r.get("design_name"), r.get("tool_used"),
                r.get("notes"), *r.get("issues_encountered", []),
                *r.get("fixes_applied", [])])

        docs = [_tokens(free_text(r)) for r in recs]
        n = len(recs)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1

        def idf(t: str) -> float:
            return math.log(n / df[t]) + 1.0 if t in df else 0.0

        qv = {t: q.count(t) * idf(t) for t in set(q)}
        qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
        scored = []
        for rec, d in zip(recs, docs):
            dv = {t: d.count(t) * idf(t) for t in set(d) if t in qv}
            dn = math.sqrt(sum(v * v for v in dv.values())) or 1.0
            score = sum(qv[t] * dv[t] for t in dv) / (qn * dn)
            if score > 0:
                scored.append({"score": round(score, 4), "record": rec})
        scored.sort(key=lambda x: -x["score"])
        return scored[:limit]

    # -- distill / QoR (vendored upstream CLIs) ---------------------------------
    def distill(self, min_records: int = 10) -> dict:
        script = VENDOR_ROOT / "plugins" / "infrastructure" / "skills" / \
            "memory-keeper" / "distill.py"
        proc = subprocess.run(
            [sys.executable, str(script), self.domain,
             "--min-records", str(min_records), "--memory-root", str(self.root)],
            capture_output=True, text=True, timeout=60)
        if proc.returncode == 2:
            return {"ok": True, "skipped": True,
                    "reason": f"fewer than {min_records} records"}
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip()[-400:]}
        return {"ok": True, "summary": json.loads(proc.stdout)}


def qor_trends(design: str, domain: str | None = None,
               root: str | Path | None = None) -> dict:
    """Cross-run QoR trending via the vendored upstream tool."""
    script = VENDOR_ROOT / "tools" / "qor_trends.py"
    cmd = [sys.executable, str(script), "--design", design,
           "--memory-root", str(resolve_memory_root(root))]
    if domain:
        cmd += ["--domain", domain]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode == 1:
        return {"ok": True, "runs_found": 0, "note": proc.stdout.strip()[-200:]}
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip()[-400:]}
    return {"ok": True, "output": proc.stdout[-4000:]}
