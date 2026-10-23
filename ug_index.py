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

from .site_paths import UG_ROOT as UG_ROOT_DEFAULT
from .manual_ingest import (
    _pack_str_col, _concat_packed, _MetaCols,
    SHARD_NNZ_BUDGET, SHARD_META_BUDGET,
)

DIM = 1 << 18
NGRAM = 2           # word 1-2 gram
CHUNK_CHARS = 1200
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 60
SHARD_TARGET_BYTES = 48 * 1024 * 1024   # strictly < 50 MiB per index file
# post_rows(i32)+post_vals(f32) per entry + terms/post_ptr amortized overhead
UG_META_STR_COLS = ("product", "doc", "section", "kind")

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_HEADING_RE = re.compile(
    r"^(?:chapter\s+\d+\.?\s+[^.]{0,80}|section\s+\d+\.?\s+[^.]{0,80}"
    r"|\d{1,2}(?:\.\d{1,2})+\.?\s+[A-Z].{0,80}"   # 3.1 / 4.2.1 sub-section
    r"|\d{1,2}\s+[A-Z][^.]{0,80})\s*$", re.I)      # 3  Coverage Flow (no dot)
_STEP_RE = re.compile(
    r"^\s*(?:step\s+\d+\s*[:.]|\d{1,2}\.\s+[A-Za-z(]|[a-h]\.\s+[A-Za-z(])", re.I)


def _ug_root() -> Path:
    return Path(os.environ.get("CHIP_AGENT_UG_ROOT", UG_ROOT_DEFAULT))


def _index_paths(root: Path) -> tuple[Path, Path]:
    return root / "ug_vectors.npz", root / "ug_chunks_meta.json"


def _shard_paths(root: Path) -> dict[str, Path]:
    d = root / "ug_index_shards"
    return {"dir": d, "manifest": d / "manifest.json"}


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
def _section_title(paras: list[str]) -> str | None:
    """A short first-line paragraph that matches a heading pattern."""
    first = paras[0].split("\n", 1)[0].strip()
    if len(first) <= 90 and _HEADING_RE.match(first):
        return first
    return None


def _steps_ratio(paras: list[str]) -> float:
    hits = sum(1 for p in paras if _STEP_RE.match(p))
    return hits / max(len(paras), 1)


def _chunks_structured(text: str) -> list[tuple[str, str, str]]:
    """Split a manual into (chunk, section_title, kind) units.

    Segmentation unit = 章节 (heading-delimited section) or 操作步骤
    (numbered/Step-N block); CHUNK_CHARS stays a packing cap only, so a
    step is never broken mid-list unless the whole section overflows.
    kind ∈ {chapter, steps, prose}.
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections: list[tuple[str, str, list[str]]] = []  # (title, kind, paras)
    cur_title, cur, cur_steps = "", [], 0
    for p in paras:
        title = _section_title([p])
        if title:
            if cur:
                kind = ("steps" if cur_steps >= 2
                        else "chapter" if cur_title else "prose")
                sections.append((cur_title, kind, cur))
            cur_title, cur, cur_steps = title, [p], 0
            continue
        if _STEP_RE.match(p):
            cur_steps += 1
        cur.append(p)
    if cur:
        kind = ("steps" if cur_steps >= 2
                else "chapter" if cur_title else "prose")
        sections.append((cur_title, kind, cur))

    out: list[tuple[str, str, str]] = []
    for title, kind, sec in sections:
        buf = ""
        emitted = [False]

        def _emit(b: str, _title=title, _kind=kind, _state=emitted):
            # a titled section always yields at least one unit: the heading
            # itself is high-value retrieval context even when the section is
            # shorter than MIN_CHUNK_CHARS
            if (not _state[0] and _title) or len(b.strip()) >= MIN_CHUNK_CHARS:
                out.append((b.strip(), _title, _kind))
                _state[0] = True
        for p in sec:
            while len(p) > CHUNK_CHARS * 2:
                _emit(p[:CHUNK_CHARS])
                p = p[CHUNK_CHARS - OVERLAP_CHARS:]
            if buf and len(buf) + len(p) > CHUNK_CHARS:
                _emit(buf)
                buf = buf[-OVERLAP_CHARS:] + "\n" + p
            else:
                buf = (buf + "\n" + p) if buf else p
        if buf.strip():
            _emit(buf)
    return out


def _chunks_of(text: str) -> list[str]:
    """Back-compat wrapper: plain texts of the structured chunks."""
    return [c for c, _t, _k in _chunks_structured(text)]


def _iter_docs(root: Path):
    for gz in sorted(root.rglob(".*.txt.gz")):
        product = ("vcs" if "/vcs/" in str(gz)
                    else "verdi" if "/verdi/" in str(gz)
                    else "uvm" if "/uvm/" in str(gz) else None)
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
        for i, (chunk, section, kind) in enumerate(_chunks_structured(text)):
            toks = _tokens(chunk)
            if not toks:
                continue
            hs = np.array([_hash(t) for t in toks], dtype=np.int64)
            uq, cnt = np.unique(hs, return_counts=True)
            rows.append(uq)
            vals.append(cnt.astype(np.float32))
            df_counts[uq] += 1.0
            meta.append({"product": product, "doc": doc, "chunk": i,
                         "section": section, "kind": kind})

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

    # inverted postings over tf-idf rows, persisted as < 50 MiB shards
    sharding = _write_sharded_index(root, indptr, indices, data, meta)
    global _CACHE
    if _CACHE is not None and _CACHE[0] == root:
        _CACHE = None
    return {
        "docs": len({(m["product"], m["doc"]) for m in meta}),
        "chunks": n,
        "dim": DIM,
        "index_dir": str(_shard_paths(root)["dir"]),
        **sharding,
        "build_seconds": round(time.time() - t0, 1),
    }


def _write_sharded_index(root: Path, indptr: np.ndarray, indices: np.ndarray,
                         data: np.ndarray, meta: list[dict]) -> dict:
    """Write postings + packed-meta shards (v2, every file < 50 MiB)."""
    sp = _shard_paths(root)
    sp["dir"].mkdir(parents=True, exist_ok=True)
    for stale in sp["dir"].glob("*"):
        if stale.is_file() and stale.name != "manifest.json":
            stale.unlink()
    n = len(meta)
    nnz_per_row = np.diff(indptr)
    meta_bytes = np.fromiter(
        (sum(len(str(m.get(k, "")).encode("utf-8")) + 1
             for k in UG_META_STR_COLS) + 8 for m in meta),
        dtype=np.int64, count=n)
    shards: list[dict] = []
    a = 0
    max_file_bytes = 0
    while a < n:
        b, acc, macc = a, 0, 0
        while b < n and (
                (acc == 0 and macc == 0)
                or (acc + int(nnz_per_row[b]) <= SHARD_NNZ_BUDGET
                    and macc + int(meta_bytes[b]) <= SHARD_META_BUDGET)):
            acc += int(nnz_per_row[b])
            macc += int(meta_bytes[b])
            b += 1
        seg_idx = indices[indptr[a]:indptr[b]]
        seg_val = data[indptr[a]:indptr[b]]
        seg_row = np.repeat(np.arange(a, b, dtype=np.int32), nnz_per_row[a:b])
        order = np.argsort(seg_idx, kind="stable")
        s_idx, s_row, s_val = seg_idx[order], seg_row[order], seg_val[order]
        starts = np.flatnonzero(np.r_[True, s_idx[1:] != s_idx[:-1]])
        sid = f"{len(shards):03d}"
        files = {}
        for arr_name, arr in (
                ("terms", s_idx[starts].astype(np.int32)),
                ("post_ptr", np.r_[starts, len(s_idx)].astype(np.int64)),
                ("post_rows", s_row.astype(np.int32)),
                ("post_vals", s_val.astype(np.float32))):
            fname = f"shard_{sid}.{arr_name}.npy"
            np.save(sp["dir"] / fname, arr)
            files[arr_name] = fname
            max_file_bytes = max(max_file_bytes,
                                 (sp["dir"] / fname).stat().st_size)
        mname = f"meta_{sid}.npz"
        mcols: dict = {}
        for k in UG_META_STR_COLS:
            d, o = _pack_str_col([m.get(k, "") for m in meta[a:b]])
            mcols[f"cd_{k}"] = d
            mcols[f"co_{k}"] = o
        mcols["chunk"] = np.asarray([m["chunk"] for m in meta[a:b]],
                                    dtype=np.int64)
        np.savez(sp["dir"] / mname, **mcols)
        max_file_bytes = max(max_file_bytes,
                             (sp["dir"] / mname).stat().st_size)
        shards.append({**files, "meta": mname, "row_start": int(a),
                       "row_end": int(b), "rows": int(b - a), "nnz": int(acc)})
        a = b
    manifest = {"format": "sharded-postings-v2", "dim": DIM, "n_rows": n,
                "nnz": int(len(indices)), "target_max_bytes": SHARD_TARGET_BYTES,
                "shards": shards, "created_unix": time.time()}
    if max_file_bytes >= SHARD_TARGET_BYTES:
        raise RuntimeError(
            f"index shard {max_file_bytes} bytes >= {SHARD_TARGET_BYTES}")
    sp["manifest"].write_text(json.dumps(manifest))
    npz_path, meta_path = _index_paths(root)
    for legacy in (npz_path, meta_path):
        if legacy.exists():
            legacy.unlink()
    return {"shards": len(shards), "max_file_bytes": max_file_bytes}


# ---------------------------------------------------------------- search
def _load(root: Path):
    global _CACHE
    if _CACHE is not None and _CACHE[0] == root:
        return _CACHE[1]
    npz_path, meta_path = _index_paths(root)
    sp = _shard_paths(root)
    if sp["manifest"].exists():
        sm = json.loads(sp["manifest"].read_text())
        if sm.get("format") == "sharded-postings-v2":
            shard_arrays = []
            packed = {k: [] for k in UG_META_STR_COLS}
            chunks = []
            for s in sm["shards"]:
                shard_arrays.append({k: np.load(
                    sp["dir"] / s[k], mmap_mode="r")
                    for k in ("terms", "post_ptr", "post_rows", "post_vals")})
                mz = np.load(sp["dir"] / s["meta"])
                for k in UG_META_STR_COLS:
                    packed[k].append((mz[f"cd_{k}"], mz[f"co_{k}"]))
                chunks.append(mz["chunk"])
                mz.close()
            arrs = {"shards": shard_arrays, "n_rows": sm["n_rows"], "v2": True}
            meta = _MetaCols({**{k: _concat_packed(v)
                                 for k, v in packed.items()},
                              "chunk": np.concatenate(chunks)}, internal=())
        else:
            from concurrent.futures import ThreadPoolExecutor
            files = [sp["dir"] / s["npz"] for s in sm["shards"]]

            def _load_one(p: Path) -> dict:
                z = np.load(p)
                arrs = {k: z[k] for k in ("terms", "post_ptr",
                                          "post_rows", "post_vals")}
                z.close()
                return arrs

            with ThreadPoolExecutor(max_workers=4) as ex:
                shard_arrays = list(ex.map(_load_one, files))
            arrs = {"shards": shard_arrays, "n_rows": sm["n_rows"]}
            meta = [m for s in sm["shards"]
                    for m in json.loads((sp["dir"] / s["meta"]).read_text())]
    elif npz_path.exists() and meta_path.exists():
        z = np.load(npz_path)
        arrs = {k: z[k] for k in
                ("indptr", "indices", "data", "terms", "post_ptr",
                 "post_rows", "post_vals")}
        z.close()
        meta = json.loads(meta_path.read_text())
    else:
        return None
    _CACHE = (root, (arrs, meta))
    return arrs, meta


_CACHE = None


def search(query: str, product: str | None = None, top_k: int = 5,
           root: Path | None = None, kind: str | None = None) -> dict:
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

    seen = {}
    for h in hs:
        seen[h] = seen.get(h, 0) + 1.0
    hit_rows = []
    hit_vals = []
    shard_list = z["shards"] if "shards" in z else [z]
    for shard in shard_list:
        arr_terms = shard["terms"]
        post_ptr = shard["post_ptr"]
        post_rows = shard["post_rows"]
        post_vals = shard["post_vals"]
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

    if isinstance(meta, _MetaCols):
        # v2: vectorized candidate filtering + bounded top-k preselection
        cand = np.flatnonzero(scores > 0)
        if product:
            cand = cand[meta.eq_mask("product", product, cand)]
        if kind:
            cand = cand[meta.eq_mask("kind", kind, cand)]
        pre = top_k * 8
        if len(cand) > pre:
            part = np.argpartition(-scores[cand], pre - 1)[:pre]
            thresh = scores[cand[part]].min()
            # keep every boundary tie: exact same order as a full stable sort
            cand = cand[scores[cand] >= thresh]
        cand = np.sort(cand)                      # ascending row ids
        order = cand[np.argsort(-scores[cand], kind="stable")]
    else:
        order = np.argsort(-scores)
    hits = []
    for idx in order:
        if scores[idx] <= 0:
            break
        m = (meta.row(int(idx)) if isinstance(meta, _MetaCols)
             else meta[int(idx)])
        hits.append({"score": round(float(scores[idx]), 4),
                     "product": str(m["product"]), "doc": str(m["doc"]),
                     "chunk": int(m["chunk"]),
                     "section": m.get("section", ""),
                     "kind": m.get("kind", "prose")})
        if len(hits) >= top_k:
            break
    return {"query": query, "hits": hits}


def index_status(root: Path | None = None) -> dict:
    root = root or _ug_root()
    npz_path, meta_path = _index_paths(root)
    sp = _shard_paths(root)
    if sp["manifest"].exists():
        sm = json.loads(sp["manifest"].read_text())
        if sm.get("format") == "sharded-postings-v2":
            packed = {k: [] for k in UG_META_STR_COLS}
            chunks = []
            for s in sm["shards"]:
                mz = np.load(sp["dir"] / s["meta"])
                for k in UG_META_STR_COLS:
                    packed[k].append((mz[f"cd_{k}"], mz[f"co_{k}"]))
                chunks.append(mz["chunk"])
                mz.close()
            meta = _MetaCols({**{k: _concat_packed(v)
                                 for k, v in packed.items()},
                              "chunk": np.concatenate(chunks)}, internal=())
        else:
            meta = [m for s in sm["shards"]
                    for m in json.loads((sp["dir"] / s["meta"]).read_text())]
        by_prod: dict[str, int] = {}
        n = len(meta)
        docs: set = set()
        if isinstance(meta, _MetaCols):
            pd, po = meta.cols["product"]
            dd, do = meta.cols["doc"]
            for i in range(n):
                p = bytes(pd[po[i]:po[i + 1]]).decode("utf-8")
                doc = bytes(dd[do[i]:do[i + 1]]).decode("utf-8")
                by_prod[p] = by_prod.get(p, 0) + 1
                docs.add((p, doc))
        else:
            for m in meta:
                by_prod[m["product"]] = by_prod.get(m["product"], 0) + 1
                docs.add((m["product"], m["doc"]))
        sizes = [p.stat().st_size for p in sorted(sp["dir"].glob("*"))
                 if p.is_file() and p.name != "manifest.json"]
        return {
            "built": True, "root": str(root),
            "docs": len(docs), "chunks": n, "chunks_by_product": by_prod,
            "shards": len(sm["shards"]),
            "max_shard_bytes": max(sizes, default=0),
            "index_dir": str(sp["dir"]),
            "dim": DIM,
        }
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
