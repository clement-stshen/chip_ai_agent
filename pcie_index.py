"""PCIe OVM User Guide corpus: PDF -> structured units -> SFT + vector index.

Pipeline stage 1/2 of the manual-to-agent-skill chain:
  * extract()   - pypdf text extraction to a side .txt.gz (idempotent)
  * build()     - structured chunks (chapter / steps / prose) + hashed
                  tf-idf inverted index, reusing ug_index internals
  * search()    - cosine-ish relevance search with kind filter
  * generate_sft() - heuristic Alpaca QA records from the structured units,
                  merged with the curated pcie_ovm_sft.jsonl (curated first)

All artifacts live under chip_ai_agent/corpus/pcie_ovm/.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path

import numpy as np

from . import ug_index

PKG_DIR = Path(__file__).parent
CORPUS_ROOT = PKG_DIR / "corpus" / "pcie_ovm"
INDEX_ROOT = CORPUS_ROOT / "ug"
DEFAULT_PDF = ("/mnt/hgfs/temp_tools/pcie_doc/"
               "pcie_svt_ovm_user_guide.pdf")
CURATED_SFT = CORPUS_ROOT / "pcie_ovm_sft.jsonl"
MAX_GENERATED = 400

_CODE_RE = re.compile(
    r"(class\s+\w+\s+extends|`ovm_do|function\s+new|task\s+body|"
    r"factory\.set_|_cfg\.\w+\s*=|setenv\s+OVM_HOME|\+define\+)", re.M)
_CHAPTER_RE = re.compile(r"^Chapter\s+\d+", re.I)
_NUMBERED_RE = re.compile(r"^(\d{1,2})[.)]\s+(\S.*)$")
_STEP_LINE_RE = re.compile(r"^\s*\d{1,2}[.)]\s+\S")
_TITLE_WORD_RE = re.compile(r"^[A-Z][a-z0-9]+(?:[\s/&+()-][A-Z][a-z0-9]+)*$")
_LEGAL_RE = re.compile(r"^(Copyright|Confidential|Proprietary)", re.I)
# page furniture: running headers/footers, page numbers, TOC dotted lines
_FURNITURE_RE = re.compile(
    r"^(Feedback|Contents|www\.synopsys\.com|\d{1,4}|\s*)$")
_TOC_RE = re.compile(r"\.\s*\.\s*\.|\.{4,}")


def _looks_like_title(title: str) -> bool:
    """Section title: short, no hex noise, word-shaped."""
    if len(title) > 80 or re.search(r"\b[0-9A-F]{8}\b", title):
        return False
    return bool(_TITLE_WORD_RE.match(title))


def _strip_furniture(paras: list[str]) -> list[str]:
    out = []
    for p in paras:
        lines = [l for l in p.splitlines()
                 if not _FURNITURE_RE.match(l) and not _TOC_RE.search(l)]
        p2 = "\n".join(lines).strip()
        if p2:
            out.append(p2)
    return out


def _structured_units(text: str) -> list[dict]:
    """Stage 1b: heading/step-aware units (章节/步骤/代码/正文).

    Two-pass design: first mark runs of consecutively-numbered step lines
    (1. 2. 3. ...) so procedure lists are emitted as kind=steps units.
    Only "Chapter N" headings produce kind=chapter units; other numbered
    titles classify as sections. Page furniture and TOC noise are stripped.
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    paras = [p for p in paras
             if not _LEGAL_RE.match(p) and not p.startswith("©")]
    paras = _strip_furniture(paras)
    n = len(paras)

    # pass 1: step-run spans (consecutive paras numbered 1,2,3,...)
    step_run = [False] * n
    i = 0
    while i < n:
        m = _NUMBERED_RE.match(paras[i])
        if m and int(m.group(1)) == 1 and len(paras[i].splitlines()) == 1:
            j = i + 1
            expect = 2
            span = [i]
            while j < n:
                mj = _NUMBERED_RE.match(paras[j])
                if mj and int(mj.group(1)) == expect \
                        and len(paras[j].splitlines()) == 1:
                    span.append(j)
                    expect += 1
                    j += 1
                else:
                    break
            if len(span) >= 2:
                for k in span:
                    step_run[k] = True
                i = j
                continue
        i += 1

    units: list[dict] = []
    chapter = ""
    section = ""
    buf: list[str] = []

    def _flush():
        nonlocal buf
        body = "\n\n".join(buf).strip()
        buf = []
        if not body:
            return
        lines = body.splitlines()
        n_steps = sum(1 for l in lines if _STEP_LINE_RE.match(l))
        kind = ("steps" if n_steps >= 2 else
                "code" if _CODE_RE.search(body) else "prose")
        units.append({"chapter": chapter, "section": section,
                      "kind": kind, "text": body[:2400]})

    i = 0
    last_chapter = ""
    while i < n:
        p = paras[i]
        if step_run[i]:
            _flush()
            body = "\n\n".join(paras[k] for k in range(i, n) if step_run[k])
            i = next((k for k in range(i + 1, n) if not step_run[k]), n)
            units.append({"chapter": chapter, "section": section,
                          "kind": "steps", "text": body[:2400]})
            continue
        first_line = p.splitlines()[0].strip()
        if _CHAPTER_RE.match(first_line):
            # PDF page headers repeat the chapter title on every page:
            # emit a chapter unit only when the title changes
            if first_line != last_chapter:
                _flush()
                last_chapter = first_line
                chapter = first_line[:120]
                section = ""
                units.append({"chapter": chapter, "section": "",
                              "kind": "chapter", "text": chapter})
            rest = "\n".join(p.splitlines()[1:]).strip()
            i += 1
            if rest:
                buf.append(rest)
            continue
        mnum = _NUMBERED_RE.match(p)
        if (mnum and len(p.splitlines()) == 1
                and _looks_like_title(mnum.group(2))):
            _flush()
            section = p.strip()[:120]      # numbered title -> section
            i += 1
            continue
        words = p.split()
        is_heading = (len(words) <= 14 and not p.endswith(".")
                      and words and words[0][0].isupper()
                      and any(w[0].isupper() for w in words[1:])
                      and not _CODE_RE.search(p))
        if is_heading:
            _flush()
            section = p.strip()[:120]
            i += 1
            continue
        buf.append(p)
        if sum(len(x) for x in buf) > 1600:
            _flush()
        i += 1
    _flush()
    return units


def _pdf_path() -> Path:
    return Path(os.environ.get("CHIP_AGENT_PCIE_PDF", DEFAULT_PDF))


def _txt_gz() -> Path:
    return INDEX_ROOT / ".pcie_svt_ovm_user_guide.txt.gz"


def extract(pdf: str | Path | None = None) -> dict:
    """Stage 1a: PDF -> side text cache (idempotent)."""
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    src = Path(pdf) if pdf else _pdf_path()
    out = _txt_gz()
    if out.exists() and out.stat().st_size > 0:
        return {"pages": None, "cached": True, "path": str(out)}
    from pypdf import PdfReader

    reader = PdfReader(str(src))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = "\n\n".join(parts)
    with gzip.open(out, "wb") as f:
        f.write(text.encode("utf-8"))
    return {"pages": len(reader.pages), "cached": False,
            "chars": len(text), "path": str(out)}


def structured_units() -> list[dict]:
    """Return the cached stage-1 structured units (extract first)."""
    with gzip.open(_txt_gz(), "rb") as f:
        text = f.read().decode("utf-8", "replace")
    return _structured_units(text)


def _hash(tok: str) -> int:
    return ug_index._hash(tok)


def build(pdf: str | Path | None = None) -> dict:
    """Stage 1 complete: extract + structured units + vector index."""
    ex = extract(pdf)
    units = structured_units()
    (INDEX_ROOT / "structured_units.jsonl").write_text(
        "\n".join(json.dumps(u, ensure_ascii=False) for u in units),
        encoding="utf-8")

    rows: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    meta: list[dict] = []
    df = np.zeros(ug_index.DIM, dtype=np.float64)
    for i, u in enumerate(units):
        toks = ug_index._tokens(u["text"])
        if not toks:
            continue
        hs = np.unique(np.array([_hash(t) for t in toks], dtype=np.int64))
        rows.append(hs)
        df[hs] += 1.0
        meta.append({"doc": "pcie_svt_ovm_user_guide", "chunk": i,
                     "chapter": u["chapter"], "section": u["section"],
                     "kind": u["kind"], "excerpt": u["text"][:400]})
    n = len(meta)
    if n == 0:
        return {"error": "no structured units produced"}
    idf = np.log((n + 1.0) / (df + 1.0)) + 1.0
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum([len(r) for r in rows], out=indptr[1:])
    indices = np.concatenate(rows)
    data = idf[indices].astype(np.float32)          # binary tf weighting
    for i in range(n):
        seg = data[indptr[i]:indptr[i + 1]]
        data[indptr[i]:indptr[i + 1]] = seg / (np.linalg.norm(seg) or 1.0)
    np.savez_compressed(INDEX_ROOT / "pcie_vectors.npz",
                        indptr=indptr, indices=indices, data=data)
    (INDEX_ROOT / "pcie_chunks_meta.json").write_text(json.dumps(meta))
    global _CACHE
    _CACHE = None
    return {"pages": ex.get("pages"), "units": n,
            "kinds": {k: sum(1 for m in meta if m["kind"] == k)
                      for k in ("chapter", "steps", "code", "prose")},
            "npz": str(INDEX_ROOT / "pcie_vectors.npz")}


_CACHE = None


def _load():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    npz = INDEX_ROOT / "pcie_vectors.npz"
    meta = INDEX_ROOT / "pcie_chunks_meta.json"
    if not npz.exists() or not meta.exists():
        return None
    z = np.load(npz)
    arrs = {k: z[k] for k in ("indptr", "indices", "data")}
    z.close()
    _CACHE = (arrs, json.loads(meta.read_text()))
    return _CACHE


def search(query: str, top_k: int = 5, kind: str | None = None) -> dict:
    loaded = _load()
    if loaded is None:
        return {"error": "pcie index not built; run pcie_index.build() first"}
    arrs, meta = loaded
    toks = ug_index._tokens(query)
    if not toks:
        return {"error": "empty query"}
    hs = np.array([_hash(t) for t in toks], dtype=np.int64)
    indptr, indices, data = arrs["indptr"], arrs["indices"], arrs["data"]
    qset = set(hs.tolist())
    scores = np.zeros(len(meta), dtype=np.float64)
    # binary query terms: score every posting whose term id matches
    mask = np.isin(indices, hs)
    rows = np.searchsorted(indptr, np.flatnonzero(mask), side="right") - 1
    np.add.at(scores, rows, data[mask])
    hits = []
    for idx in np.argsort(-scores):
        if scores[idx] <= 0 or len(hits) >= top_k:
            break
        m = meta[int(idx)]
        if kind and m["kind"] != kind:
            continue
        hits.append({"score": round(float(scores[idx]), 4), **m})
    return {"query": query, "hits": hits}


def generate_sft() -> dict:
    """Stage 2: heuristic Alpaca QA from units, merged with curated set."""
    units = structured_units()
    seen_instructions = set()
    records: list[dict] = []
    if CURATED_SFT.exists():
        for line in CURATED_SFT.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            seen_instructions.add(r["instruction"])
            records.append(r)
    n_curated = len(records)
    for u in units:
        if len(records) - n_curated >= MAX_GENERATED:
            break
        title = u["section"] or u["chapter"] or "the PCIe OVM VIP"
        if u["kind"] == "steps":
            inst = (f"Describe the steps for {title} in the Synopsys "
                    f"PCIe OVM User Guide.")
        elif u["kind"] == "code":
            inst = (f"Show the SystemVerilog OVM code pattern for {title} "
                    f"in the PCIe OVM User Guide.")
        else:
            inst = (f"Explain {title} in the PCIe OVM User Guide.")
        if inst in seen_instructions:
            continue
        seen_instructions.add(inst)
        records.append({"instruction": inst, "input": "",
                        "output": u["text"]})
    with CURATED_SFT.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"curated": n_curated, "generated": len(records) - n_curated,
            "total": len(records), "path": str(CURATED_SFT)}


def status() -> dict:
    npz = INDEX_ROOT / "pcie_vectors.npz"
    meta = INDEX_ROOT / "pcie_chunks_meta.json"
    ok = npz.exists() and meta.exists()
    return {"built": ok,
            "units": len(json.loads(meta.read_text())) if ok else 0,
            "sft_lines": (sum(1 for _ in CURATED_SFT.open(encoding="utf-8"))
                          if CURATED_SFT.exists() else 0),
            "pdf": str(_pdf_path())}


if __name__ == "__main__":
    import sys
    print(json.dumps(build() if len(sys.argv) < 2 or sys.argv[1] == "build"
                     else generate_sft() if sys.argv[1] == "sft"
                     else status(), ensure_ascii=False, indent=2))
