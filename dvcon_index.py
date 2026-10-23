"""DVCon 2025/2026 论文语料向量索引.

切分单元 (kind):
  - abstract : 种子论文条目 (title/authors/venue/year/summary)
  - method   : 方法描述段 (we propose / method / approach / algorithm ...)
  - conclusion: 结论/未来工作段 (in conclusion / future work ...)
  - paragraph: 其余正文段落

来源:
  1. 种子语料 dvcon_seed_corpus.json (真实 DVCon US 2025/2026 论文条目)
  2. 用户放置于 DVCON 根目录的 .md/.txt/.pdf (全文, PDF 用 pypdf)

实现: 复用 ug_index 的哈希 TF-IDF 倒排 (独立 DIM/缓存, 纯 numpy).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
from pathlib import Path

import numpy as np

from . import ug_index

DIM = 1 << 16
KINDS = ("abstract", "method", "conclusion", "paragraph")
SEED_PATH = Path(__file__).with_name("dvcon_seed_corpus.json")

# track tags: auto-derived from title+summary keywords (no manual labeling)
_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ai", ("llm", "agentic", "agent", "generative", "machine learning",
            "knowledge graph")),
    ("verification", ("uvm", "assertion", "formal", "coverage", "regression",
                      "testbench", "verification", "debug", "vplan")),
    ("low-power", ("power", "upf", "isolation", "retention", "low-power")),
    ("cdc", ("cdc", "clock-domain", "multi-clock", "reset", "x-propagation",
             "x propagation")),
    ("timing", ("sdc", "timing", "constraint")),
    ("signoff", ("sign-off", "signoff", "equivalence", "eco", "drc", "lvs",
                 "tape-out", "tapeout", "compliance")),
    ("stimulus", ("portable stimulus", "pss", "stimulus")),
)


def _hash(tok: str) -> int:
    """Reuse ug_index blake2 hashing, bucketed into dvcon_index.DIM."""
    return ug_index._hash(tok) % DIM


def tags_for(entry: dict) -> list[str]:
    """Auto-classify a paper entry into track tags (ordered, deduped)."""
    text = " ".join([entry.get("title", ""), entry.get("summary", "")]).lower()
    tags = []
    for tag, kws in _TAG_RULES:
        if any(k in text for k in kws):
            tags.append(tag)
    return tags or ["verification"]

_METHOD_RE = re.compile(
    r"\b(?:we (?:propose|present|introduce|develop)|"
    r"our (?:method|approach|framework|flow)|"
    r"(?:method|approach|algorithm|architecture|framework) (?:we|described))",
    re.I)
_CONCL_RE = re.compile(
    r"\b(?:in conclusion|in summary|future work|"
    r"as future (?:work|directions)|we conclude)", re.I)


def _dvcon_root() -> Path:
    return Path(os.environ.get(
        "CHIP_AGENT_DVCON_ROOT",
        str(Path(__file__).parent / "dvcon")))


def _index_paths(root: Path) -> tuple[Path, Path]:
    return root / "dvcon_vectors.npz", root / "dvcon_chunks_meta.json"


# ---------------------------------------------------------------- sources
def _seed_entries() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def _read_files(root: Path) -> list[dict]:
    """用户放置的全文文档 -> {title, year, text}."""
    docs: list[dict] = []
    for pat in ("*.md", "*.txt", "*.pdf"):
        for f in sorted(root.rglob(pat)):
            try:
                if f.suffix == ".pdf":
                    from pypdf import PdfReader
                    pages = []
                    for page in PdfReader(str(f)).pages:
                        try:
                            pages.append(page.extract_text() or "")
                        except Exception:
                            pages.append("")
                    text = "\n\n".join(pages)
                else:
                    text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            m = re.search(r"(?:[^0-9]|^)(202[4-9])(?:[^0-9]|$)", f.name)
            # underscore/hyphen separators are word/non-word chars;
            # the plain \b form missed "FVDebug_2026.txt"-style names
            docs.append({"title": f.stem, "year": m.group(1) if m else "",
                         "text": text})
    return docs


# ---------------------------------------------------------------- chunking
def _units(text: str) -> list[tuple[str, str]]:
    """正文 -> [(kind, paragraph)]"""
    out = []
    for p in re.split(r"\n\s*\n", text):
        p = p.strip()
        if len(p) < 40:
            continue
        if _CONCL_RE.search(p):
            kind = "conclusion"
        elif _METHOD_RE.search(p):
            kind = "method"
        else:
            kind = "paragraph"
        out.append((kind, p))
    return out


# ---------------------------------------------------------------- build
def build(root: Path | None = None) -> dict:
    root = root or _dvcon_root()
    root.mkdir(parents=True, exist_ok=True)
    npz_path, meta_path = _index_paths(root)
    t0 = time.time()

    rows: list[np.ndarray] = []
    meta: list[dict] = []
    df = np.zeros(DIM, dtype=np.float64)

    for entry in _seed_entries():
        toks = ug_index._tokens(
            " ".join([entry.get("title", ""), entry.get("summary", "")]))
        if toks:
            hs = np.array([_hash(t) for t in toks], dtype=np.int64)
            uq, cnt = np.unique(hs, return_counts=True)
            rows.append(uq)
            df[uq] += 1.0
            meta.append({
                "kind": "abstract", "year": str(entry.get("year", "")),
                "title": entry.get("title", ""),
                "authors": entry.get("authors", ""),
                "venue": entry.get("venue", "DVCon US"),
            "doc": "seed", "excerpt": entry.get("summary", "")[:400],
            "tags": tags_for(entry)})

    for doc in _read_files(root):
        for kind, para in _units(doc["text"]):
            toks = ug_index._tokens(para)
            if not toks:
                continue
            hs = np.array([_hash(t) for t in toks], dtype=np.int64)
            uq, cnt = np.unique(hs, return_counts=True)
            rows.append(uq)
            df[uq] += 1.0
            meta.append({
                "kind": kind, "year": doc["year"], "title": doc["title"],
                "authors": "", "venue": "", "doc": doc["title"],
                "excerpt": para[:400], "tags": []})
            _ = cnt

    n = len(meta)
    if n == 0:
        return {"error": "no dvcon corpus entries or documents found"}

    idf = np.log((n + 1.0) / (df + 1.0)) + 1.0
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum([len(r) for r in rows], out=indptr[1:])
    indices = np.concatenate(rows)
    tf = 1.0 + np.log(np.concatenate(
        [r.astype(np.float64) for r in rows]))
    data = (tf * idf[indices]).astype(np.float32)
    for i in range(n):
        s, e = int(indptr[i]), int(indptr[i + 1])
        norm = float(np.linalg.norm(data[s:e])) or 1.0
        data[s:e] /= norm

    order = np.argsort(indices, kind="stable")
    s_ind = indices[order]
    s_rows = np.repeat(np.arange(n, dtype=np.int64),
                       np.diff(indptr))[order]
    s_dat = data[order]
    b = np.flatnonzero(np.r_[True, s_ind[1:] != s_ind[:-1]])

    np.savez_compressed(
        npz_path,
        indptr=indptr, indices=indices, data=data,
        terms=s_ind[b], post_ptr=np.r_[b, len(s_ind)],
        post_rows=s_rows, post_vals=s_dat)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False))
    return {"papers": len(_seed_entries()), "chunks": n, "dim": DIM,
            "npz_bytes": npz_path.stat().st_size,
            "build_seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- search
_CACHE: tuple[Path, tuple] | None = None


def _load(root: Path):
    global _CACHE
    if _CACHE is not None and _CACHE[0] == root:
        return _CACHE[1]
    npz_path, meta_path = _index_paths(root)
    if not npz_path.exists() or not meta_path.exists():
        if build(root).get("error"):
            return None
    z = np.load(npz_path)
    arrs = {k: z[k] for k in ("indptr", "indices", "data", "terms",
                              "post_ptr", "post_rows", "post_vals")}
    z.close()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    _CACHE = (root, (arrs, meta))
    return arrs, meta


def search(query: str, year: str | int | None = None, kind: str | None = None,
           tag: str | None = None, top_k: int = 5,
           root: Path | None = None) -> dict:
    root = root or _dvcon_root()
    loaded = _load(root)
    if loaded is None:
        return {"error": "dvcon index not available"}
    z, meta = loaded
    toks = ug_index._tokens(query)
    if not toks:
        return {"error": "empty query"}
    hs = np.array([_hash(t) for t in toks], dtype=np.int64)
    q = np.zeros(DIM, dtype=np.float64)
    np.add.at(q, hs, 1.0)
    qn = float(np.linalg.norm(q)) or 1.0

    terms, post_ptr = z["terms"], z["post_ptr"]
    post_rows, post_vals = z["post_rows"], z["post_vals"]
    seen: dict[int, float] = {}
    for h in hs:
        seen[int(h)] = seen.get(int(h), 0.0) + 1.0
    hit_rows, hit_vals = [], []
    for h, tf_q in seen.items():
        pos = int(np.searchsorted(terms, h))
        if pos >= len(terms) or int(terms[pos]) != h:
            continue
        s, e = int(post_ptr[pos]), int(post_ptr[pos + 1])
        hit_rows.append(post_rows[s:e])
        hit_vals.append(post_vals[s:e].astype(np.float64) * tf_q)
    scores = np.zeros(len(meta), dtype=np.float64)
    if hit_rows:
        scores = np.bincount(np.concatenate(hit_rows),
                             weights=np.concatenate(hit_vals),
                             minlength=len(meta))
    scores /= qn

    yfilter = str(year) if year is not None else None
    hits = []
    for idx in np.argsort(-scores):
        if scores[idx] <= 0:
            break
        m = meta[int(idx)]
        if kind and m["kind"] != kind:
            continue
        if tag and tag not in m.get("tags", []):
            continue
        if yfilter and m.get("year", "") != yfilter:
            continue
        hits.append({"score": round(float(scores[idx]), 4),
                     "kind": m["kind"], "year": m.get("year", ""),
                     "title": m.get("title", ""),
                     "authors": m.get("authors", ""),
                     "venue": m.get("venue", ""),
                     "tags": m.get("tags", []),
                     "doc": m.get("doc", ""), "excerpt": m.get("excerpt", "")})
        if len(hits) >= top_k:
            break
    return {"query": query, "hits": hits}


def status(root: Path | None = None) -> dict:
    root = root or _dvcon_root()
    npz_path, meta_path = _index_paths(root)
    if not npz_path.exists():
        return {"built": False, "root": str(root),
                "seed_papers": len(_seed_entries())}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    by_kind: dict[str, int] = {}
    by_year: dict[str, int] = {}
    for m in meta:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        y = m.get("year", "") or "unknown"
        by_year[y] = by_year.get(y, 0) + 1
    return {"built": True, "root": str(root), "chunks": len(meta),
            "chunks_by_kind": by_kind, "chunks_by_year": by_year,
            "seed_papers": len(_seed_entries())}


# ---------------------------------------------------------------- SFT corpus
CORPUS_ROOT = Path(__file__).parent / "corpus" / "dvcon"
SFT_PATH = CORPUS_ROOT / "dvcon_sft.jsonl"
MAX_GENERATED = 400

# curated QA (grounded in seed entries that drive the six paper recipes)
_CURATED = (
    {"instruction": "What is Saarthi and how does it automate formal "
                    "verification?",
     "input": "",
     "output": "Saarthi (DVCon 2025) is presented as the first AI formal "
               "verification engineer: an LLM agent loop that reads specs "
               "and RTL, writes and proves SVA properties, and iterates on "
               "counterexamples until closure, reducing manual formal "
               "bring-up effort."},
    {"instruction": "How can specifications be matched to verification "
                    "plans using AI?",
     "input": "",
     "output": "The DVCon 2026 'AI Agent-based Specification Matching "
               "System' extracts requirements from the spec, builds a "
               "knowledge-graph/semantic index over RTL and verification "
               "items, and matches each requirement to tests/covergroups, "
               "surfacing spec-coverage gaps before regression."},
    {"instruction": "What methodology does DVCon recommend for LLM-assisted "
                    "verification IP creation?",
     "input": "",
     "output": "Papers such as 'Towards Automated Verification IP "
               "Instantiation via LLMs' (DVCon 2025) generate VIP "
               "configurations from interface specs with an LLM, then "
               "validate the instantiation through compile, UVM connect "
               "checks and smoke simulation, iterating on feedback until "
               "the environment builds cleanly."},
)


def generate_sft(root: Path | None = None) -> dict:
    """Alpaca QA corpus from DVCon seed entries + full-text units.

    Per seed paper one abstract-level QA; full-text documents contribute
    method/conclusion/paragraph QA following the Step 39b conversion chain
    (段落/方法描述/结论 -> instruction-output pairs). Records are written
    as JSONL; regeneration is deterministic and overwrite-in-place.
    """
    CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict] = [dict(r) for r in _CURATED]
    seen = {r["instruction"] for r in records}

    for entry in sorted(_seed_entries(), key=lambda e: (e["year"], e["title"])):
        if len(records) - len(_CURATED) >= MAX_GENERATED:
            break
        inst = (f"Summarize the {entry.get('venue', 'DVCon US')} "
                f"{entry.get('year', '')} paper "
                f"'{entry.get('title', '')}'.")
        if inst in seen:
            continue
        seen.add(inst)
        records.append({"instruction": inst, "input": "",
                        "output": entry.get("summary", "")})

    n_seed_qa = len(records) - len(_CURATED)
    n_unit_qa = 0
    for doc in _read_files(root or _dvcon_root()):
        title = doc["title"]
        for kind, para in _units(doc["text"]):
            if len(records) - len(_CURATED) >= MAX_GENERATED:
                break
            if kind == "method":
                inst = (f"Describe the verification methodology proposed in "
                        f"'{title}'.")
            elif kind == "conclusion":
                inst = (f"What are the conclusions and future-work "
                        f"directions in '{title}'?")
            else:
                inst = f"Explain key points from '{title}' (DVCon paper)."
            if inst in seen:
                continue
            seen.add(inst)
            records.append({"instruction": inst, "input": "",
                            "output": para})
            n_unit_qa += 1

    with SFT_PATH.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"curated": len(_CURATED), "seed_qa": n_seed_qa,
            "unit_qa": n_unit_qa, "total": len(records),
            "path": str(SFT_PATH)}


# ---------------------------------------------------------------- distill
def digest(root: Path | None = None) -> dict:
    """主动记忆: 论文语料蒸馏成 dvcon_knowledge.md (按 track tag 分节).

    蒸馏产物被 chip_agent_recall 注入 verification 域上下文, 让 agent 在
    无需再次检索的情况下带着最新的 DVCon 方法论记忆工作. 幂等 + 确定性
    (按 year, title 排序), 语料变化后重跑即更新.
    """
    root = root or _dvcon_root()
    entries = sorted(_seed_entries(), key=lambda e: (e["year"], e["title"]))
    lines = ["# DVCon 2025/2026 方法论蒸馏 (memory-keeper)", ""]
    by_tag: dict[str, list[dict]] = {}
    for e in entries:
        for t in tags_for(e):
            by_tag.setdefault(t, []).append(e)
    for tag in sorted(by_tag):
        lines.append(f"## track: {tag}")
        lines.append("")
        for e in by_tag[tag]:
            lines.append(f"- **{e['title']}** ({e['authors']}, {e['year']}): "
                         f"{e['summary']}")
        lines.append("")
    out = root / "dvcon_knowledge.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(out), "papers": len(entries),
            "tracks": sorted(by_tag), "bytes": out.stat().st_size}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="DVCon paper vector index")
    ap.add_argument("op",
                    choices=["build", "search", "status", "digest", "sft"])
    ap.add_argument("query", nargs="*", default=[])
    ap.add_argument("--year"); ap.add_argument("--kind"); ap.add_argument("--top-k", type=int)
    ap.add_argument("--tag")
    a = ap.parse_args()
    if a.op == "build":
        print(json.dumps(build(), ensure_ascii=False))
    elif a.op == "search":
        print(json.dumps(search(" ".join(a.query), year=a.year, kind=a.kind, tag=a.tag,
                                top_k=a.top_k or 5), ensure_ascii=False, indent=2))
    elif a.op == "digest":
        print(json.dumps(digest(), ensure_ascii=False, indent=2))
    elif a.op == "sft":
        print(json.dumps(generate_sft(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
