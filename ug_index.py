"""UG 向量检索索引 (VCS + Verdi 用户手册).

纯 numpy 实现:
  - 抽取 VCS PDF 文本为旁侧 .txt.gz (幂等, Verdi 已有现成文本直接用)
  - 段落切分 chunk (~1200 字符带重叠) -> 哈希 TF-IDF 稀疏向量 (CSR, dim=2^18)
  - 倒排 posting (term -> rowids/vals) 存入同一 npz, 查询 np.add.at 打分
  - 索引: <ug_root>/ug_vectors.npz + ug_chunks_meta.json
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

import numpy as np

UG_ROOT_DEFAULT = "/tools/Synopsys/temp/ug"
DIM = 1 << 18
NGRAM = 2           # word 1-2 gram
CHUNK_CHARS = 1200
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 60

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _ug_root() -> Path:
    return Path(os.environ.get("CHIP_AGENT_UG_ROOT", UG_ROOT_DEFAULT))


def _index_paths(root: Path) -> tuple[Path, Path]:
    return root / "ug_vectors.npz", root / "ug_chunks_meta.json"


# ---------------------------------------------------------------- extraction
def extract_pdfs(root: Path | None = None) -> dict:
    """抽取 VCS PDF -> 旁侧隐藏 .txt.gz; Verdi 已有文本跳过. 幂等."""
    root = root or _ug_root()
    from pypdf import PdfReader

    stats = {"extracted": 0, "skipped": 0, "failed": 0}
    for pdf in sorted(root.rglob("*.pdf")):
        out = pdf.with_name("." + pdf.stem + ".txt.gz")
        if out.exists() and out.stat().st_size > 0:
            stats["skipped"] += 1
            continue
        try:
            reader = PdfReader(str(pdf))
            pages = []
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or "")
                except Exception:
                    pages.append("")
            text = "\n\n".join(pages)
            out.write_bytes(gzip.compress(text.encode("utf-8", "replace")))
            stats["extracted"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            print(f"[ug_index] skip broken {pdf.name}: {exc}")
    return stats


# ---------------------------------------------------------------- chunking
def _chunks_of(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paras:
        while len(p) > CHUNK_CHARS * 2:
            out.append(p[:CHUNK_CHARS])
            p = p[CHUNK_CHARS - OVERLAP_CHARS:]
        if buf and len(buf) + len(p) > CHUNK_CHARS:
            out.append(buf)
            buf = buf[-OVERLAP_CHARS:] + "\n" + p
        else:
            buf = (buf + "\n" + p) if buf else p
    if len(buf) >= MIN_CHUNK_CHARS:
        out.append(buf)
    return out


def _iter_docs(root: Path):
    for gz in sorted(root.rglob(".*.txt.gz")):
        product = "vcs" if "/vcs/" in str(gz) else ("verdi" if "/verdi/" in str(gz) else None)
        if product is None:
            continue
        try:
            text = gzip.decompress(gz.read_bytes()).decode("utf-8", "replace")
        except Exception:
            continue
        yield product, gz.stem.lstrip(".").removesuffix(".txt"), text


def _tokens(text: str) -> list[str]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    toks = list(words)
    for a, b in zip(words, words[1:]):
        toks.append(a + "_" + b)
    return toks


def _hash(tok: str) -> int:
    return int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big") % DIM


# ---------------------------------------------------------------- build
def build_index(root: Path | None = None) -> dict:
    root = root or _ug_root()
    npz_path, meta_path = _index_paths(root)
    t0 = time.time()

    rows: list[np.ndarray] = []      # indices per chunk
    vals: list[np.ndarray] = []      # counts per chunk
    meta: list[dict] = []
    df_counts = np.zeros(DIM, dtype=np.float64)  # doc freq over chunks

    for product, doc, text in _iter_docs(root):
        for i, chunk in enumerate(_chunks_of(text)):
            toks = _tokens(chunk)
            if not toks:
                continue
            hs = np.array([_hash(t) for t in toks], dtype=np.int64)
            uq, cnt = np.unique(hs, return_counts=True)
            rows.append(uq)
            vals.append(cnt.astype(np.float32))
            df_counts[uq] += 1.0
            meta.append({"product": product, "doc": doc, "chunk": i})

    n = len(meta)
    if n == 0:
        return {"error": "no documents found under " + str(root)}

    idf = np.log((n + 1.0) / (df_counts + 1.0)) + 1.0
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum([len(r) for r in rows], out=indptr[1:])
    indices = np.concatenate(rows)
    tf_vals = np.concatenate(vals)
    tf = 1.0 + np.log(tf_vals)
    data = (tf * idf[indices]).astype(np.float32)
    norms = np.zeros(n, dtype=np.float32)
    for i in range(n):
        norms[i] = np.linalg.norm(data[indptr[i]:indptr[i + 1]]) or 1.0
    # normalize rows in-place via segments (loop over chunks is fine at build)
    for i in range(n):
        data[indptr[i]:indptr[i + 1]] /= norms[i]

    # inverted postings over tf-idf rows
    order = np.argsort(indices, kind="stable")
    s_ind = indices[order]
    s_rows = np.repeat(np.arange(n, dtype=np.int64), np.diff(indptr))[order]
    s_dat = data[order]
    b = np.flatnonzero(np.r_[True, s_ind[1:] != s_ind[:-1]])
    terms = s_ind[b]
    post_ptr = np.r_[b, len(s_ind)]
    post_rows = s_rows
    post_vals = s_dat

    np.savez_compressed(
        npz_path, indptr=indptr, indices=indices, data=data,
        terms=terms, post_ptr=post_ptr, post_rows=post_rows, post_vals=post_vals,
    )
    meta_path.write_text(json.dumps(meta))
    return {
        "docs": len({(m["product"], m["doc"]) for m in meta}),
        "chunks": n,
        "dim": DIM,
        "npz_bytes": npz_path.stat().st_size,
        "build_seconds": round(time.time() - t0, 1),
    }


# ---------------------------------------------------------------- search
def _load(root: Path):
    global _CACHE
    if _CACHE is not None and _CACHE[0] == root:
        return _CACHE[1]
    npz_path, meta_path = _index_paths(root)
    if not npz_path.exists() or not meta_path.exists():
        return None
    z = np.load(npz_path)
    arrs = {k: z[k] for k in
            ("indptr", "indices", "data", "terms", "post_ptr",
             "post_rows", "post_vals")}
    z.close()
    meta = json.loads(meta_path.read_text())
    _CACHE = (root, (arrs, meta))
    return arrs, meta


_CACHE = None


def search(query: str, product: str | None = None, top_k: int = 5,
           root: Path | None = None) -> dict:
    root = root or _ug_root()
    loaded = _load(root)
    if loaded is None:
        return {"error": "UG index not built; run chip_ug_index(op='build') first"}
    z, meta = loaded
    q = np.zeros(DIM, dtype=np.float64)
    toks = _tokens(query)
    if not toks:
        return {"error": "empty query"}
    hs = np.array([_hash(t) for t in toks], dtype=np.int64)
    np.add.at(q, hs, 1.0)
    qn = np.linalg.norm(q) or 1.0

    terms = z["terms"]; post_ptr = z["post_ptr"]
    post_rows = z["post_rows"]; post_vals = z["post_vals"]
    seen = {}
    for h in hs:
        seen[h] = seen.get(h, 0) + 1.0
    arr_terms = terms
    hit_rows = []
    hit_vals = []
    for h, tf_q in seen.items():
        pos = int(np.searchsorted(arr_terms, h))
        if pos >= len(arr_terms) or arr_terms[pos] != h:
            continue
        s, e = int(post_ptr[pos]), int(post_ptr[pos + 1])
        hit_rows.append(post_rows[s:e])
        hit_vals.append(post_vals[s:e].astype(np.float64) * tf_q)
    scores = np.zeros(len(meta), dtype=np.float64)
    if hit_rows:
        all_rows = np.concatenate(hit_rows)
        all_vals = np.concatenate(hit_vals)
        scores = np.bincount(all_rows, weights=all_vals, minlength=len(meta))
    scores /= qn

    order = np.argsort(-scores)
    hits = []
    for idx in order:
        m = meta[int(idx)]
        if product and m["product"] != product:
            continue
        if scores[idx] <= 0:
            break
        hits.append({"score": round(float(scores[idx]), 4),
                     "product": m["product"], "doc": m["doc"],
                     "chunk": m["chunk"]})
        if len(hits) >= top_k:
            break
    return {"query": query, "hits": hits}


def index_status(root: Path | None = None) -> dict:
    root = root or _ug_root()
    npz_path, meta_path = _index_paths(root)
    if not npz_path.exists():
        return {"built": False, "root": str(root)}
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else []
    by_prod: dict[str, int] = {}
    for m in meta:
        by_prod[m["product"]] = by_prod.get(m["product"], 0) + 1
    return {
        "built": True, "root": str(root),
        "docs": len({(m["product"], m["doc"]) for m in meta}),
        "chunks": len(meta), "chunks_by_product": by_prod,
        "npz_bytes": npz_path.stat().st_size,
        "dim": DIM,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="UG vector index")
    ap.add_argument("op", choices=["extract", "build", "search", "status"])
    ap.add_argument("query", nargs="*", default=[])
    ap.add_argument("--product", choices=["vcs", "verdi"])
    a = ap.parse_args()
    if a.op == "extract":
        print(json.dumps(extract_pdfs()))
    elif a.op == "build":
        print(json.dumps(build_index()))
    elif a.op == "search":
        print(json.dumps(search(" ".join(a.query), product=a.product), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(index_status(), ensure_ascii=False, indent=2))
