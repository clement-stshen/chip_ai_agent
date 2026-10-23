"""UVM 1.2 source-level knowledge tools (integrated from the UVM source-code
knowledge MCP; Apache-2.0 UVM source, distilled concept cards).

Structured tools (class/hierarchy/method/macro/file) run straight off the
vendored sv_index.json. Semantic search uses the project's hash-TF-IDF sparse
index (same stack as ug_index/dvcon_index) instead of embedding models, so the
whole capability stays zero-heavy-dependency and fully offline.

Data root: CHIP_AGENT_UVM_SRC_ROOT (default: package-local uvm_src_kb/).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

import hashlib
import json
import re
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from .site_paths import UVM_SRC_ROOT

PKG_DIR = Path(__file__).resolve().parent
from . import ug_index as _ug
PKG_DIR = Path(__file__).resolve().parent

DIM = 1 << 18                                   # hashed-token space (2^18)
MAX_CARD_LEN = 3000
TOP_K_SOURCE = 6
TOP_K_CURATED = 4


# ---------------------------------------------------------------- data
@lru_cache(maxsize=1)
def _sv_index() -> dict:
    p = UVM_SRC_ROOT / "sv_index.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _cards() -> list[dict]:
    p = UVM_SRC_ROOT / "concept_cards.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _class_map() -> dict:
    return {c["name"]: c for c in _sv_index().get("classes", [])}


def _method_map() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for m in _sv_index().get("methods", []):
        out.setdefault(m["class_name"], []).append(m)
    return out


def _files_map() -> dict[str, str]:
    return _sv_index().get("files", {})


def _hierarchy() -> dict[str, list[str]]:
    h: dict[str, list[str]] = {}
    for c in _sv_index().get("classes", []):
        parent = c.get("parent") or "__root__"
        h.setdefault(parent, [])
        if c["name"] not in h[parent]:
            h[parent].append(c["name"])
        h.setdefault(c["name"], [])
    return h


def _ancestors(name: str, cmap: dict) -> list[str]:
    chain, seen, cur = [], set(), name
    while cur and cur not in seen:
        seen.add(cur)
        cls = cmap.get(cur)
        if cls and cls.get("parent"):
            chain.append(cls["parent"])
            cur = cls["parent"]
        else:
            break
    return chain


def _descendants(name: str, h: dict, depth: int = 0) -> list[str]:
    if depth >= 10:
        return []
    out = list(h.get(name, []))
    for child in h.get(name, []):
        out.extend(_descendants(child, h, depth + 1))
    return out


def _rel(p: str) -> str:
    return p if not p.startswith("/") else p.split("uvm_source/")[-1]


def _not_found(cls: str) -> str:
    return (f"Class '{cls}' not found in UVM 1.2 source.\n"
            "Tip: use chip_uvm_search to find similar names.")


# ---------------------------------------------------------------- structured
def search_source(pattern, file_filter="", case_sensitive=False,
                  context_lines=3, max_results=30) -> str:
    files = _files_map()
    if not files:
        return "UVM source index not found (CHIP_AGENT_UVM_SRC_ROOT)."
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return f"Invalid regex pattern: {e}"
    results, total = [], 0
    for rel, content in files.items():
        if file_filter and file_filter.lower() not in rel.lower():
            continue
        if total >= max_results:
            break
        lines = content.splitlines()
        fm = []
        for i, line in enumerate(lines):
            if total >= max_results:
                break
            if rx.search(line):
                s, e = max(0, i - context_lines), min(len(lines), i + context_lines + 1)
                fm.append("\n".join(
                    f"{'>>>' if j == i else '   '} {j+1:4d}: {lines[j]}"
                    for j in range(s, e)))
                total += 1
        if fm:
            results.append(f"\n{'='*60}\nFile: {rel}\n{'='*60}")
            results.extend(fm)
    if not results:
        return f"No matches found for pattern: '{pattern}'"
    hdr = f"Found {total} match(es)"
    if total >= max_results:
        hdr += f" (showing first {max_results})"
    return hdr + "\n" + "\n\n---\n".join(results)


def get_class_definition(class_name: str) -> str:
    cmap = _class_map()
    cls = cmap.get(class_name)
    if cls is None:
        lname = class_name.lower()
        for n, c in cmap.items():
            if n.lower() == lname:
                cls = c
                break
    if cls is None:
        return _not_found(class_name)
    header = (
        f"// ── {cls['name']} ────────────────────────────────\n"
        f"// File : {_rel(cls['file_path'])}\n"
        f"// Lines: {cls['line_start']}–{cls['line_end']}\n"
        + (f"// Extends: {cls['parent']}\n" if cls.get("parent") else "")
        + (f"// Comment: {cls['comment']}\n" if cls.get("comment") else "")
        + "// ─────────────────────────────────────────────\n\n")
    return header + cls["body"]


def get_class_hierarchy(class_name: str, direction: str = "both") -> str:
    cmap, h = _class_map(), _hierarchy()
    if class_name not in cmap and class_name != "uvm_void":
        cands = [n for n in cmap if class_name.lower() in n.lower()]
        if cands:
            return (f"Class '{class_name}' not found. Did you mean one of:\n"
                    + "\n".join(f"  • {c}" for c in sorted(cands)[:10]))
        return _not_found(class_name)
    lines = []
    if direction in ("up", "both"):
        anc = _ancestors(class_name, cmap)
        if anc:
            lines.append("Ancestor chain (parent → grandparent → …):")
            lines.append(f"  {class_name}")
            for i, a in enumerate(anc):
                lines.append("  " + "  " * i + f"└─ {a}")
        else:
            lines.append(f"  {class_name}  (no parent / base class)")
    if direction in ("down", "both"):
        if lines:
            lines.append("")
        children = h.get(class_name, [])
        desc = _descendants(class_name, h)
        lines.append(f"Direct subclasses of {class_name} ({len(children)}):")
        for child in sorted(children):
            gc = h.get(child, [])
            suffix = f"  [{len(gc)} subclasses]" if gc else ""
            lines.append(f"  • {child}{suffix}")
        if not children:
            lines.append("  (no known subclasses in UVM 1.2 source)")
    return "\n".join(lines)


def list_methods(class_name: str) -> str:
    cmap, mmap = _class_map(), _method_map()
    if class_name not in cmap:
        return _not_found(class_name)
    methods = mmap.get(class_name, [])
    if not methods:
        return f"No methods found in {class_name} (may be defined via macros)."
    lines = [f"Methods of {class_name} ({len(methods)} total):"]
    fns = [m for m in methods if m["kind"] == "function"]
    tks = [m for m in methods if m["kind"] == "task"]
    if fns:
        lines.append("\nFunctions:")
        for m in fns:
            v = "virtual " if m.get("is_virtual") else ""
            ret = f"→ {m['return_type']}" if m.get("return_type") and m["return_type"] != "void" else ""
            cm = f"  // {m['comment']}" if m.get("comment") else ""
            lines.append(f"  {v}function {m['name']}(){ret}{cm}")
    if tks:
        lines.append("\nTasks:")
        for m in tks:
            v = "virtual " if m.get("is_virtual") else ""
            cm = f"  // {m['comment']}" if m.get("comment") else ""
            lines.append(f"  {v}task {m['name']}(){cm}")
    return "\n".join(lines)


def get_method_source(class_name: str, method_name: str) -> str:
    cmap, mmap = _class_map(), _method_map()
    if class_name not in cmap:
        return _not_found(class_name)
    tgt = next((m for m in mmap.get(class_name, []) if m["name"] == method_name), None)
    if tgt is None:
        avail = [m["name"] for m in mmap.get(class_name, [])]
        return (f"Method '{method_name}' not found in {class_name}.\n"
                f"Available methods: {', '.join(sorted(avail)[:20])}")
    header = (
        f"// ── {class_name}::{tgt['name']} ─────────────────\n"
        f"// File : {_rel(tgt['file_path'])}\n"
        f"// Lines: {tgt['line_start']}–{tgt['line_end']}\n"
        + (f"// {tgt['comment']}\n" if tgt.get("comment") else "")
        + "// ─────────────────────────────────────────────\n\n")
    return header + tgt["body"]


def list_all_classes(filter_str: str = "") -> str:
    cmap = _class_map()
    classes = list(cmap.values())
    if filter_str:
        fl = filter_str.lower()
        classes = [c for c in classes if fl in c["name"].lower()]
    if not classes:
        return f"No classes matching '{filter_str}' found in UVM 1.2."
    classes.sort(key=lambda c: c["name"])
    lines = [f"UVM 1.2 classes ({len(classes)} total):"]
    for c in classes:
        pi = f" extends {c['parent']}" if c.get("parent") else ""
        lines.append(f"  {c['name']}{pi}  [{_rel(c['file_path'])}:{c['line_start']}]")
    return "\n".join(lines)


def get_file_content(relative_path: str, start_line: int = 1, end_line: int = 0) -> str:
    files = _files_map()
    if not files:
        return "UVM source index not found (CHIP_AGENT_UVM_SRC_ROOT)."
    rp = relative_path.replace("\\", "/")
    content, matched = files.get(rp), rp
    if content is None:
        for rel, c in files.items():
            if rp.lower() in rel.lower():
                content, matched = c, rel
                break
    if content is None:
        return f"File not found: {relative_path}"
    lines = content.splitlines()
    s = max(0, start_line - 1)
    e = len(lines) if end_line <= 0 else min(end_line, len(lines))
    numbered = [f"{i+1:4d}: {line}" for i, line in enumerate(lines[s:e], start=s)]
    return f"// {matched}  (lines {s+1}–{s+len(numbered)})\n" + "\n".join(numbered)


def list_files(directory_filter: str = "") -> str:
    files = _files_map()
    if not files:
        return "UVM source index not found (CHIP_AGENT_UVM_SRC_ROOT)."
    if directory_filter:
        df = directory_filter.lower()
        files = {r: c for r, c in files.items() if df in r.lower()}
    if not files:
        return f"No files found matching filter: '{directory_filter}'"
    lines, cur = [], None
    for rel in sorted(files):
        parts = rel.replace("\\", "/").split("/")
        parent = "/".join(parts[:-1]) if len(parts) > 1 else "."
        if parent != cur:
            cur = parent
            lines.append(f"\n[{parent}/]")
        lines.append(f"  {parts[-1]}  ({len(files[rel].encode()) // 1024} KB)")
    return f"UVM 1.2 source files ({len(files)} total):" + "\n".join(lines)


def get_macro_definition(macro_name: str) -> str:
    name = macro_name.lstrip("`")
    return search_source(
        pattern=rf"`define\s+{re.escape(name)}\b",
        file_filter="macros", context_lines=5, max_results=5)


# ---------------------------------------------------------------- semantic
def _docs() -> list[dict]:
    """(kind, meta) docs: concept cards + class headers + methods + macros."""
    out = []
    cmap = _class_map()
    for card in _cards():
        text = card.get("text", "").strip()
        if not text:
            continue
        topic = text.splitlines()[0][:120]
        out.append({"kind": "curated", "topic": topic,
                    "excerpt": text[:600],
                    "text": text[:MAX_CARD_LEN]})
    for c in cmap.values():
        hdr = (f"Class: {c['name']}"
               + (f" extends {c['parent']}" if c.get("parent") else "")
               + f"\nFile: {_rel(c['file_path'])} "
                 f"Lines: {c['line_start']}-{c['line_end']}")
        out.append({"kind": "class_header", "class_name": c["name"],
                    "parent_class": c.get("parent", ""),
                    "file": _rel(c["file_path"]),
                    "line_start": c["line_start"], "line_end": c["line_end"],
                    "text": hdr + "\n" + c.get("body", "")[:MAX_CARD_LEN]})
    for m in _sv_index().get("methods", []):
        hdr = (f"Class: {m['class_name']}"
               + (f" extends {cmap[m['class_name']]['parent']}"
                  if m["class_name"] in cmap and cmap[m['class_name']].get("parent")
                  else "")
               + f"\nMethod: {'virtual ' if m.get('is_virtual') else ''}"
                 f"{m['kind']} {m['name']}"
               + f"\nFile: {_rel(m['file_path'])} "
                 f"Lines: {m['line_start']}-{m['line_end']}")
        out.append({"kind": "method", "class_name": m["class_name"],
                    "parent_class": cmap.get(m["class_name"], {}).get("parent", ""),
                    "method_name": m["name"], "method_kind": m["kind"],
                    "file": _rel(m["file_path"]),
                    "line_start": m["line_start"], "line_end": m["line_end"],
                    "text": hdr + "\n" + m.get("body", "")[:MAX_CARD_LEN]})
    for m in _sv_index().get("macros", []):
        out.append({"kind": "macro", "macro_name": m["name"],
                    "file": _rel(m.get("file_path", "")),
                    "line_start": m.get("line_number", ""),
                    "text": f"Macro: `{m['name']}\n"
                            f"File: {_rel(m.get('file_path', ''))}\n"
                            + m.get("definition", "")[:MAX_CARD_LEN]})
    return out


def _index_paths():
    return (UVM_SRC_ROOT / "uvm_kb_vectors.npz",
            UVM_SRC_ROOT / "uvm_kb_meta.json")


def _digest() -> str:
    h = hashlib.sha256()
    h.update(b"uvm_kb_v2")                  # bump on index-layout changes
    for f in ("sv_index.json", "concept_cards.json"):
        h.update((UVM_SRC_ROOT / f).read_bytes())
    return h.hexdigest()[:16]


def _load_or_build() -> tuple[dict, dict]:
    """meta_by_docid + search structures; rebuilds when inputs change."""
    npz_path, meta_path = _index_paths()
    want = _digest()
    try:
        npz = np.load(npz_path, allow_pickle=False)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("digest") == want:
            return {"npz": npz, "meta": meta["docs"]}, {}
    except Exception:
        pass
    docs = _docs()
    rows, tfs, mrows, df = [], [], [], np.zeros(DIM, dtype=np.float64)
    for i, d in enumerate(docs):
        toks = _ug._tokens(d["text"])
        if not toks:
            continue                       # skip: npz rows must align with meta
        hs = np.array([_ug._hash(t) for t in toks], dtype=np.int64)
        uq, cnt = np.unique(hs, return_counts=True)
        rows.append(uq)
        tfs.append(cnt)
        df[uq] += 1.0
        mrows.append({"kind": d["kind"], **{k: v for k, v in d.items()
                                            if k not in ("text", "kind")}})
    n = len(mrows)
    idf = np.log((n + 1.0) / (df + 1.0)) + 1.0
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum([len(r) for r in rows], out=indptr[1:])
    indices = np.concatenate(rows)
    data = (1.0 + np.log(np.concatenate(tfs).astype(np.float64))) \
        * idf[indices]
    for i in range(n):
        s, e = int(indptr[i]), int(indptr[i + 1])
        norm = float(np.linalg.norm(data[s:e])) or 1.0
        data[s:e] /= norm
    order = np.argsort(indices, kind="stable")
    s_ind = indices[order]
    s_rows = np.repeat(np.arange(n, dtype=np.int64), np.diff(indptr))[order]
    s_dat = data[order]
    b = np.flatnonzero(np.r_[True, s_ind[1:] != s_ind[:-1]])
    np.savez_compressed(npz_path, indptr=indptr, indices=s_ind,
                        data=s_dat, rowmap=s_rows, bounds=b, dim=DIM, idf=idf)
    meta_path.write_text(json.dumps(
        {"digest": want, "built": time.time(), "docs": mrows},
        ensure_ascii=False), encoding="utf-8")
    return {"npz": np.load(npz_path, allow_pickle=False), "meta": mrows}, {}


@lru_cache(maxsize=1)
def _kb() -> tuple[dict, list]:
    idx, _ = _load_or_build()
    return idx, idx["meta"]


def _rank(query: str, kind_filter: str | None, top_k: int,
          exclude: set | None = None,
          exclude_kinds: set | None = None) -> list[tuple[float, dict, dict]]:
    idx, meta = _kb()
    npz = idx["npz"]
    toks = _ug._tokens(query)
    if not toks:
        return []
    qh = np.array([_ug._hash(t) for t in toks], dtype=np.int64)
    uq, cnt = np.unique(qh, return_counts=True)
    scores = np.zeros(npz["indptr"].shape[0] - 1, dtype=np.float64)
    for h_, c_ in zip(uq, cnt):
        lo, hi = np.searchsorted(npz["indices"], [h_, h_ + 1])
        seg_rows = npz["rowmap"][lo:hi]
        seg_dat = npz["data"][lo:hi]
        for r, v in zip(seg_rows, seg_dat):
            scores[r] += float(v) * float(c_)
    qw = np.array([float(c_) * float(npz["idf"][h_]) for h_, c_ in zip(uq, cnt)])
    qn = float(np.linalg.norm(qw)) or 1.0
    out = []
    for i in np.argsort(scores)[::-1]:
        if scores[i] <= 0:
            break
        m = meta[i]
        if exclude_kinds and m.get("kind") in exclude_kinds:
            continue                     # rank within the other doc set only
        if kind_filter and m.get("kind") != kind_filter:
            continue
        if exclude and i in exclude:
            continue
        out.append((float(scores[i] / qn), m, {"row": i}))
        if len(out) >= top_k:
            break
    return out


def _sim(score: float, top: float) -> float:
    """Relative relevance: percent of the top hit's score."""
    return round(100.0 * score / top, 1) if top > 0 else 0.0


def _fmt_source(hit, score, rank, top):
    m = hit[1]
    sim = _sim(score, top)
    if m["kind"] == "method":
        inh = f" (extends {m['parent_class']})" if m.get("parent_class") else ""
        title = f"{m['class_name']}{inh} :: {m['method_name']}  [{m['method_kind']}]"
    elif m["kind"] == "macro":
        title = f"`{m['macro_name']}  [macro]"
    elif m["kind"] == "class_header":
        inh = f" extends {m['parent_class']}" if m.get("parent_class") else ""
        title = f"class {m['class_name']}{inh}  [declaration + members]"
    else:
        title = m.get("file", "")
    rng = f"{m.get('line_start')}-{m.get('line_end')}"
    return (f"\n[{rank}] {title}  (similarity: {sim}%)\n"
            f"    File: {m.get('file', '')}  Lines: {rng}")


def _fmt_curated(hit, score, rank, top):
    m = hit[1]
    sim = _sim(score, top)
    return (f"\n[{rank}] {m.get('topic', 'general')}  (similarity: {sim}%)\n"
            + "-" * 50 + "\n" + m.get("excerpt", ""))


def semantic_search(query: str, top_k: int = 6, source_only: bool = False) -> str:
    curated = ([] if source_only else
               _rank(query, "curated", min(top_k, TOP_K_CURATED)))
    # source docs are ranked within their own doc set (exclude curated),
    # mirroring the two-collection query design of the original knowledge MCP
    source = _rank(query, None, min(top_k, TOP_K_SOURCE),
                   exclude_kinds={"curated"})
    if not curated and not source:
        return f"No results found for: '{query}'"
    top = max([s for s, _, _ in curated + source] or [1.0])
    out = [f"Semantic search results for: '{query}'", "=" * 70]
    if curated:
        out.append("\n## Expert Knowledge  (distilled concept cards)")
        out.append("=" * 70)
        for i, (score, m, extra) in enumerate(curated, 1):
            out.append(_fmt_curated((score, m, extra), score, i, top))
    if source:
        out.append("\n\n## UVM 1.2 Source Code")
        out.append("=" * 70)
        for i, (score, m, extra) in enumerate(source, 1):
            out.append(_fmt_source((score, m, extra), score, i, top))
    return "\n".join(out)


def explain_uvm_concept(concept: str) -> str:
    expanded = f"UVM {concept} implementation source code explanation mechanism"
    return semantic_search(expanded, top_k=8)


# ---------------------------------------------------------------------------
# UVM 1.2 Analysis Notes search (from uvm-source-code-1.2-knowledge-mcp)
# ---------------------------------------------------------------------------

_NOTES_CACHE = None

def _notes_index():
    """Load UVM analysis notes vector index (lazy, cached)."""
    global _NOTES_CACHE
    if _NOTES_CACHE is not None:
        return _NOTES_CACHE
    notes_dir = PKG_DIR / "corpus" / "uvm_knowledge_notes"
    npz = notes_dir / "uvm_notes_vectors.npz"
    meta_f = notes_dir / "uvm_notes_meta.json"
    units_f = notes_dir / "uvm_notes_structured_units.jsonl"
    if not npz.exists() or not meta_f.exists():
        return None
    import numpy as _np
    z = np.load(npz)
    arrays = {k: z[k] for k in ("terms", "post_ptr", "post_rows", "post_vals")}
    z.close()
    meta = json.loads(meta_f.read_text(encoding="utf-8"))
    units = [json.loads(l) for l in units_f.read_text(encoding="utf-8").splitlines() if l.strip()]
    _NOTES_CACHE = (arrays, meta, units)
    return _NOTES_CACHE


# Token/hash helpers for notes search

def _tokens(text: str) -> list[str]:
    words = [w.lower() for w in re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]").findall(text)]
    toks = list(words)
    for a, b in zip(words, words[1:]):
        toks.append(a + "_" + b)
    return toks

def _hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big") % (1 << 18)


def search_notes(query: str, top_k: int = 5, subsystem: str | None = None,
                 kind: str | None = None) -> dict:
    """Search UVM 1.2 analysis notes (1834 units from 210 source analysis files)."""
    loaded = _notes_index()
    if loaded is None:
        return {"error": "UVM notes index not found; run build_uvm_notes_index() first"}
    arrays, meta, units = loaded
    toks = _tokens(query)
    if not toks:
        return {"error": "empty query"}
    q_counts = Counter(_hash(t) for t in toks)
    scores = np.zeros(len(meta), dtype=np.float64)
    terms = arrays["terms"]; pp = arrays["post_ptr"]; pr = arrays["post_rows"]; pv = arrays["post_vals"]
    for term, qtf in q_counts.items():
        pos = int(np.searchsorted(terms, term))
        if pos < len(terms) and int(terms[pos]) == term:
            s, e = int(pp[pos]), int(pp[pos + 1])
            np.add.at(scores, pr[s:e], pv[s:e].astype(np.float64) * qtf)
    qnorm = math.sqrt(sum(v * v for v in q_counts.values())) or 1.0
    scores /= qnorm
    hits = []
    for idx in np.argsort(-scores):
        if len(hits) >= top_k or scores[idx] <= 0:
            break
        m = meta[int(idx)]
        if subsystem and m["subsystem"] != subsystem:
            continue
        if kind and m["kind"] != kind:
            continue
        unit = units[int(idx)]
        hits.append({
            "score": round(float(scores[idx]), 4),
            **m,
            "text": unit["text"][:3000],
            "text_truncated": len(unit["text"]) > 3000,
        })
    return {"query": query, "total_notes": len(meta), "hits": hits}

