"""Recursive PDF/HTML technical-manual ingestion and agent-skill generation.

The pipeline deliberately keeps four high-value retrieval granularities:
chapter/section, operating procedure, flow, and example.  It produces:

* ``inventory.json``                 - every scanned PDF/HTML candidate and why it
                                       was accepted/rejected
* ``extracted/*.txt.gz``             - deterministic text cache
* ``structured_units.jsonl``         - provenance-rich manual units
* ``model_sft.jsonl``                - Alpaca-style model-training corpus
* ``manual_vectors.npz`` + metadata  - hashed TF-IDF inverted index

The default scan root is the deployment package's parent directory (portable;
override with ``CHIP_AGENT_MANUAL_SCAN_ROOT``); output can be
redirected with ``CHIP_AGENT_TECH_MANUAL_ROOT``.  Existing hidden UG text caches
are reused when their relative source path matches, so a full 129-PDF rebuild
does not reparse nearly 500 MB of vendor PDFs.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .site_paths import UG_ROOT as UG_ROOT_DEFAULT


PKG_DIR = Path(__file__).resolve().parent
# Default scan root is the deployment parent directory (portable; no
# site-specific absolute path baked in). Override with
# CHIP_AGENT_MANUAL_SCAN_ROOT to point at another EDA documentation tree.
DEFAULT_SCAN_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = Path(os.environ.get(
    "CHIP_AGENT_TECH_MANUAL_ROOT",
    str(PKG_DIR / "corpus" / "technical_manuals"),
))
KINDS = ("chapter", "section", "steps", "flow", "example", "prose")
DIM = 1 << 18
MAX_UNIT_CHARS = 6000
UNIT_OVERLAP_CHARS = 250
MIN_UNIT_CHARS = 50
SHARD_TARGET_BYTES = 48 * 1024 * 1024   # strictly < 50 MiB per index file
# post_rows(i32)+post_vals(f32) per entry + terms/post_ptr amortized overhead
SHARD_NNZ_BUDGET = (42 * 1024 * 1024) // 8   # postings rows+vals <= 42 MiB
SHARD_META_BUDGET = 4 * 1024 * 1024           # packed meta columns <= 4 MiB
DATA_SHARD_BYTES = 45 * 1024 * 1024     # units/sft jsonl shards (< 50 MiB)

_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
_PDF_PAGE_RE = re.compile(r"^<<<PDF_PAGE (\d+)>>>$")
_CHAPTER_RE = re.compile(
    r"^(?:chapter\s+\d+(?:\s+[A-Z\u4e00-\u9fff].{0,100})?"
    r"|appendix\s+[a-z0-9]+(?:\s+[A-Z\u4e00-\u9fff].{0,100})?"
    r"|第[0-9一二三四五六七八九十百]+[章节部分].{0,100})$", re.I)
_NUMBER_HEADING_RE = re.compile(
    r"^(\d{1,2}(?:\.\d{1,4})*)[.)]?\s+(\S.{2,100})$")
_STEP_RE = re.compile(
    r"^(?:step\s+\d+\s*[:.)]|\(?(\d{1,2})\)\s+\S|\*?\[?\(?([a-h])\)?\]?\.\s+\S)",
    re.I)
_NUMBERED_STEP_RE = re.compile(r"^(\d{1,2})[.)]\s+(\S.*)$")
_TOC_DOTS_RE = re.compile(r"(?:\.\s*){3,}|\.{4,}")
_ARROW_RE = re.compile(r"(?:->|=>|→|⟶|\u2192)")
_FLOW_HINT_RE = re.compile(
    r"\b(flow|workflow|pipeline|procedure sequence|stage|phase|compile flow|"
    r"simulation flow|debug flow|verification flow)\b", re.I)
_EXAMPLE_HINT_RE = re.compile(
    r"^(?:example|sample|for example|e\.g\.|usage|code snippet|command line|"
    r"shell example|tcl example|systemverilog example)", re.I)
_CODE_RE = re.compile(
    r"(?m)^\s*(?:[%$#]\s|\$?\s*(?:vcs|verdi|urg|simv|python|make|gcc|"
    r"xrun|irun|questa|vsim|tclsh)\b|"
    r"(?:class|module|program|interface|package|function|task|typedef|"
    r"assign|initial|always|property|sequence|covergroup|import|module|"
    r"set|puts|foreach|while|if|for)\b.*[;{()]|"
    r"(?:-[a-z][\w-]*\s+|--[a-z][\w-]*(?:=|\s+)))", re.I)
_TECH_HINT_RE = re.compile(
    r"\b(user guide|user manual|reference|tutorial|application note|appnote|"
    r"chapter|section|procedure|operation|command|option|flow|example|"
    r"configuration|installation|debug|simulation|coverage|waveform|"
    r"testbench|systemverilog|uvm|eda|rtl|user\s*guide)\b", re.I)
_NOISE_PATH_RE = re.compile(
    r"(/\.git/|/__pycache__/|/node_modules/|/wheelhouse/|/\.venv/|"
    r"/corpus/technical_manuals/extracted)", re.I)


# ---------------------------------------------------------------------------
# paths / small helpers
# ---------------------------------------------------------------------------


def _scan_root(root: Path | None = None) -> Path:
    return Path(root or os.environ.get(
        "CHIP_AGENT_MANUAL_SCAN_ROOT", str(DEFAULT_SCAN_ROOT))).resolve()


def _out_root(root: Path | None = None) -> Path:
    return Path(root or os.environ.get(
        "CHIP_AGENT_TECH_MANUAL_ROOT", str(CORPUS_ROOT))).resolve()


def _artifact_paths(out: Path) -> dict[str, Path]:
    return {
        "inventory": out / "inventory.json",
        "units": out / "structured_units.jsonl",
        "sft": out / "model_sft.jsonl",
        "meta": out / "manual_chunks_meta.json",
        "vectors": out / "manual_vectors.npz",
        "manifest": out / "manifest.json",
    }


def _shard_paths(out: Path) -> dict[str, Path]:
    d = out / "manual_index_shards"
    return {"dir": d, "manifest": d / "manifest.json"}


def _units_shard_paths(out: Path) -> dict[str, Path]:
    d = out / "units_shards"
    return {"dir": d, "manifest": d / "manifest.json"}


def _sft_shard_paths(out: Path) -> dict[str, Path]:
    d = out / "sft_shards"
    return {"dir": d, "manifest": d / "manifest.json"}


class _UnitsLayout:
    """Byte-addressable logical view over sharded (or monolithic) units.

    Shard files concatenate byte-identically to the original
    ``structured_units.jsonl``, so the ``_unit_offset`` values stored in the
    index meta shards remain valid without any index rebuild.
    """

    def __init__(self, out: Path):
        self.out = out
        sp = _units_shard_paths(out)
        self.files: list[Path] = []
        self.starts: list[int] = []
        if sp["manifest"].exists():
            m = json.loads(sp["manifest"].read_text(encoding="utf-8"))
            off = 0
            for name in m["files"]:
                p = sp["dir"] / name
                self.files.append(p)
                self.starts.append(off)
                off += p.stat().st_size
        elif _artifact_paths(out)["units"].exists():
            p = _artifact_paths(out)["units"]
            self.files = [p]
            self.starts = [0]
        self.total = sum(f.stat().st_size for f in self.files)

    @property
    def available(self) -> bool:
        return bool(self.files)

    def iter_with_offsets(self) -> Iterable[tuple[dict, int]]:
        for p, start in zip(self.files, self.starts):
            with p.open("rb") as f:
                off = start
                for raw in f:
                    if raw.strip():
                        yield json.loads(raw), off
                    off += len(raw)

    def read_at(self, global_offset: int) -> dict:
        import bisect
        i = bisect.bisect_right(self.starts, global_offset) - 1
        with self.files[i].open("rb") as f:
            f.seek(global_offset - self.starts[i])
            return json.loads(f.readline())


def _split_jsonl_lines(src: Path, shard_dir: Path, stem: str) -> dict:
    """Split a jsonl file at line boundaries into < DATA_SHARD_BYTES shards.

    Concatenation of emitted shards is byte-identical to ``src`` (raw line
    bytes are copied verbatim), preserving any global byte offsets.
    """
    shard_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    sizes: list[int] = []
    records = 0
    idx = 0
    cur = None
    cur_bytes = 0
    with src.open("rb") as f:
        for raw in f:
            records += 1
            if cur is None or (cur_bytes and cur_bytes + len(raw) > DATA_SHARD_BYTES):
                if cur is not None:
                    cur.close()
                    files.append(f"{stem}_{idx:05d}.jsonl")
                    sizes.append((shard_dir / files[-1]).stat().st_size)
                    idx += 1
                cur = (shard_dir / f"{stem}_{idx:05d}.jsonl").open("wb")
                cur_bytes = 0
            cur.write(raw)
            cur_bytes += len(raw)
    if cur is not None:
        cur.close()
        files.append(f"{stem}_{idx:05d}.jsonl")
        sizes.append((shard_dir / files[-1]).stat().st_size)
    return {"files": files, "sizes": sizes,
            "total_bytes": sum(sizes), "records": records}


def _write_jsonl_sharded_from_iter(records: Iterable[dict], shard_dir: Path,
                                   stem: str) -> dict:
    """Stream records into < DATA_SHARD_BYTES jsonl shards."""
    shard_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    sizes: list[int] = []
    records_n = 0
    idx = 0
    cur = None
    cur_bytes = 0
    for rec in records:
        raw = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
        records_n += 1
        if cur is None or (cur_bytes and cur_bytes + len(raw) > DATA_SHARD_BYTES):
            if cur is not None:
                cur.close()
                files.append(f"{stem}_{idx:05d}.jsonl")
                sizes.append((shard_dir / files[-1]).stat().st_size)
                idx += 1
            cur = (shard_dir / f"{stem}_{idx:05d}.jsonl").open("wb")
            cur_bytes = 0
        cur.write(raw)
        cur_bytes += len(raw)
    if cur is not None:
        cur.close()
        files.append(f"{stem}_{idx:05d}.jsonl")
        sizes.append((shard_dir / files[-1]).stat().st_size)
    return {"files": files, "sizes": sizes,
            "total_bytes": sum(sizes), "records": records_n}


def migrate_data_shards(out: Path | None = None) -> dict:
    """Split existing monolithic units/sft jsonl into < 50 MiB shards.

    Byte-exactness is verified (concatenated sha256 == source sha256) before
    the monolithic file is removed, so index ``_unit_offset`` values survive.
    """
    out = _out_root(out)
    result: dict = {}
    for key, get_sp, stem in (
            ("units", _units_shard_paths, "units"),
            ("sft", _sft_shard_paths, "sft")):
        src = _artifact_paths(out)[key]
        sp = get_sp(out)
        if not src.exists():
            result[key] = {"migrated": False, "reason": "monolithic absent"}
            continue
        info = _split_jsonl_lines(src, sp["dir"], stem)
        h = hashlib.sha256()
        for name in info["files"]:
            h.update((sp["dir"] / name).read_bytes())
        if h.hexdigest() != hashlib.sha256(src.read_bytes()).hexdigest():
            for name in info["files"]:
                (sp["dir"] / name).unlink(missing_ok=True)
            result[key] = {"migrated": False, "error": "sha256 mismatch; aborted"}
            continue
        manifest = {"format": "jsonl-shards-v1", "stem": stem,
                    "max_target_bytes": DATA_SHARD_BYTES, **info,
                    "created_unix": time.time()}
        _write_json_atomic(sp["manifest"], manifest)
        src.unlink()
        result[key] = {"migrated": True, "shards": len(info["files"]),
                       "max_bytes": max(info["sizes"], default=0),
                       "total_bytes": info["total_bytes"],
                       "records": info["records"]}
    return result


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", value).strip("_")
    return value[:96] or "manual"


def _doc_name(path: Path) -> str:
    return re.sub(r"[_\-.]+", "_", unicodedata.normalize("NFKC", path.stem)).strip("_") or "manual"


def _product(path: Path, scan_root: Path) -> str:
    try:
        rel = path.relative_to(scan_root)
        parts = [p.lower() for p in rel.parts[:-1]]
    except ValueError:
        parts = [p.lower() for p in path.parts[:-1]]
    preferred = {"vcs", "verdi", "uvm", "chipstack", "cadence", "synopsys",
                 "siemens", "lint", "formality"}
    for p in reversed(parts):
        if p in preferred:
            return p
    for p in reversed(parts):
        if len(p) > 2 and p not in {"doc", "docs", "pdf", "html", "userguide", "user_guide"}:
            return p
    return "general"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _tokens(text: str) -> list[str]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    toks = list(words)
    for a, b in zip(words, words[1:]):
        toks.append(a + "_" + b)
    return toks


def _hash(token: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(token.encode("utf-8", "replace"), digest_size=4).digest(),
        "big") % DIM


def _write_json_atomic(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _write_jsonl_atomic(path: Path, records: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(path)
    return n


# ---------------------------------------------------------------------------
# scanning, extraction, and technical-manual classification
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    path: Path
    fmt: str
    size: int


def scan(root: Path | None = None) -> dict:
    """Recursively enumerate PDF/HTML candidates without raising on denied dirs."""
    scan_rt = _scan_root(root)
    found: list[Candidate] = []
    errors: list[dict] = []
    if not scan_rt.exists():
        return {"root": str(scan_rt), "candidates": [], "errors": [
            {"path": str(scan_rt), "error": "scan root does not exist"}]}

    for dirpath, dirnames, filenames in os.walk(scan_rt, onerror=lambda e: errors.append(
            {"path": str(getattr(e, "filename", "")), "error": str(e)})):
        dirnames[:] = sorted(d for d in dirnames
                             if not _NOISE_PATH_RE.search(f"/{dirpath}/{d}/"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            ext = path.suffix.lower()
            if ext not in {".pdf", ".html", ".htm"}:
                continue
            if _NOISE_PATH_RE.search(str(path)):
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})
                continue
            found.append(Candidate(path, "pdf" if ext == ".pdf" else "html", size))
    found.sort(key=lambda c: c.path)
    return {
        "root": str(scan_rt),
        "candidates": [
            {"path": str(c.path), "format": c.fmt, "bytes": c.size}
            for c in found
        ],
        "errors": errors,
    }


def _extract_pdf(path: Path) -> tuple[str, int, str | None]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages: list[str] = []
    for number, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:             # one broken page should not lose a manual
            text = ""
        pages.append(f"<<<PDF_PAGE {number}>>>\n{text}")
    meta_title = None
    try:
        raw_title = reader.metadata.title if reader.metadata else None
        if raw_title and str(raw_title).strip():
            meta_title = " ".join(str(raw_title).split())
    except Exception:
        pass
    return "\n\n".join(pages), len(reader.pages), meta_title


def _extract_html(path: Path) -> tuple[str, int, str | None]:
    from bs4 import BeautifulSoup
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    # Preserve code examples as visually separate blocks before get_text.
    for tag in soup.find_all(["pre", "code"]):
        marker = "MANUAL_EXAMPLE_BLOCK\n" + tag.get_text("\n", strip=True)
        tag.replace_with(f"\n\n{marker}\n\n")
    node = soup.find("main") or soup.find("article") or soup.body or soup
    text = node.get_text("\n", strip=True)
    return text, 1, title


def _external_cache(path: Path, scan_rt: Path) -> Path | None:
    """Find a same-relative hidden UG text sidecar (idempotent extraction cache)."""
    roots = [UG_ROOT_DEFAULT, Path(os.environ.get("CHIP_AGENT_UG_ROOT", str(UG_ROOT_DEFAULT)))]
    exact: list[Path] = []
    for root in roots:
        try:
            rel = path.relative_to(scan_rt)
            side = root.joinpath(rel).with_name("." + path.stem + ".txt.gz")
        except ValueError:
            side = root / f".{path.stem}.txt.gz"
        exact.append(side)
        if side.exists() and side.stat().st_size:
            return side
    # Different installation roots often retain the same vendor subtree. A
    # unique stem is sufficient for these shipped manuals; validate gzip later.
    for root in dict.fromkeys(roots):
        if not root.exists():
            continue
        for side in root.rglob(f".{path.stem}.txt.gz"):
            if side.stat().st_size:
                return side
    for side in exact:
        if side.exists() and side.stat().st_size:
            return side
    return None


def _load_or_extract_text(candidate: Candidate, scan_rt: Path, out: Path
                          ) -> tuple[str, dict]:
    text_dir = out / "extracted"
    text_dir.mkdir(parents=True, exist_ok=True)
    digest8 = hashlib.sha256(str(candidate.path).encode()).hexdigest()[:8]
    doc = _doc_name(candidate.path)
    cache = text_dir / f"{_slug(doc)}_{digest8}.txt.gz"
    extraction = "cache"
    pages = 0
    title: str | None = None
    if cache.exists() and cache.stat().st_size:
        try:
            text = gzip.decompress(cache.read_bytes()).decode("utf-8", "replace")
            return text, {"extraction": "cache", "text_cache": str(cache)}
        except Exception:
            pass

    side = _external_cache(candidate.path, scan_rt) if candidate.fmt == "pdf" else None
    if side is not None:
        try:
            text = gzip.decompress(side.read_bytes()).decode("utf-8", "replace")
            extraction = "external-ug-cache"
            pages = len(_PDF_PAGE_RE.findall(text))
        except Exception:
            side = None
    if side is None:
        if candidate.fmt == "pdf":
            text, pages, title = _extract_pdf(candidate.path)
            title = _clean_manual_title(title) if title else title
            extraction = "pypdf"
        else:
            text, pages, title = _extract_html(candidate.path)
            title = _clean_manual_title(title) if title else title
            extraction = "beautifulsoup"

    cache.write_bytes(gzip.compress(text.encode("utf-8", "replace"), compresslevel=6))
    return text, {"extraction": extraction, "text_cache": str(cache),
                  "pages": pages, "metadata_title": title}


def _technical_score(text: str, candidate: Candidate) -> tuple[int, str]:
    sample = text[:30000]
    hints = len(set(m.group(0).lower() for m in _TECH_HINT_RE.finditer(sample)))
    if candidate.fmt == "pdf":
        # PDFs under this installation are vendor/manual exports. Requiring a
        # hint or substantive technical text avoids indexing random one-page PDFs.
        if hints >= 1 and len(sample.strip()) >= 1200:
            return 100, "pdf technical manual/content"
        if len(sample.strip()) >= 8000:
            return 80, "large technical pdf"
        return 0, "pdf lacks technical-manual text"
    headings = len(re.findall(r"(?m)^(?:Chapter|Appendix|\d+(?:\.\d+)+)\b", sample, re.I))
    if hints >= 2 and headings >= 2 and len(sample.strip()) >= 1500:
        return 100, "html technical manual structure"
    if hints >= 3 and len(sample.strip()) >= 3000:
        return 80, "html technical content"
    return 0, "html app shell or non-manual page"


# ---------------------------------------------------------------------------
# text normalization and structured segmentation
# ---------------------------------------------------------------------------


def _clean_line(line: str) -> str:
    line = line.replace("\x00", "").rstrip()
    return re.sub(r"\s+", " ", line).strip()


def _normalize_text(text: str) -> tuple[str, int]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    all_lines = [l.rstrip() for l in text.splitlines()]
    repeated = Counter(
        l.strip() for l in all_lines
        if l.strip() and 3 < len(l.strip()) <= 90
    )
    furniture = {line for line, count in repeated.items() if count >= 6}
    lines: list[str] = []
    pages = max([int(m.group(1)) for l in all_lines
                 if (m := _PDF_PAGE_RE.match(l.strip()))] or [0])
    for line in all_lines:
        s = line.strip()
        if _PDF_PAGE_RE.match(s) or not s:
            lines.append("")
            continue
        if re.fullmatch(r"\d{1,5}", s):
            continue
        if s in furniture or s.lower() in {
                "table of contents", "contents", "feedback",
                "www.synopsys.com", "product version"}:
            continue
        if _TOC_DOTS_RE.search(s):
            s = _TOC_DOTS_RE.sub("", s).strip()
        lines.append(_clean_line(s))
    normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return normalized, pages


def _strip_toc_pages(text: str) -> str:
    """Drop explicit PDF TOC pages; cached UG texts already omit most furniture."""
    chunks = re.split(r"(?m)^<<<PDF_PAGE \d+>>>$", text)
    kept: list[str] = []
    for chunk in chunks:
        low = chunk.lower()
        if "table of contents" in low:
            lines = [l for l in chunk.splitlines() if l.strip()]
            headingish = sum(1 for l in lines if _parse_heading(l))
            if lines and headingish / len(lines) >= 0.55:
                continue
        kept.append(chunk)
    return "\n\n".join(kept) if len(kept) != len(chunks) else text


def _parse_heading(line: str) -> tuple[int, str, str] | None:
    """Return (level, kind, clean title), excluding TOC/trailing page numbers."""
    s = _clean_line(line)
    if not (3 <= len(s) <= 120):
        return None
    if _CHAPTER_RE.match(s):
        return (1, "chapter", s)
    m = _NUMBER_HEADING_RE.match(s)
    if m:
        number, title = m.group(1).rstrip(".)"), m.group(2).strip()
        # Single-number "1 Introduction" is a chapter; "1.1 Foo" is a section.
        # A numbered sentence with terminal punctuation is more likely a step.
        if "." in number:
            if title[-1:] not in ".;:":
                return (len(number.split(".")), "section", f"{number} {title}")
        elif not re.match(r"^\d+[.)]\s", s) and title[-1:] not in ".;":
            return (1, "chapter", f"{number} {title}")
        elif re.match(r"^\d+\s+[A-Z]", s) and len(title.split()) <= 12:
            return (1, "chapter", f"{number} {title}")
    return None


def _blocks(text: str) -> list[str]:
    return [re.sub(r"\n+", "\n", b).strip()
            for b in re.split(r"\n\s*\n", text) if b.strip()]


def _first_step_number(block: str) -> int | None:
    first = block.splitlines()[0] if block.splitlines() else ""
    m = _NUMBERED_STEP_RE.match(first)
    return int(m.group(1)) if m else None


def _group_step_blocks(blocks: list[str]) -> list[str]:
    """Join PDF paragraphs where each numbered step became its own paragraph."""
    out: list[str] = []
    i = 0
    while i < len(blocks):
        first = _first_step_number(blocks[i])
        if first != 1:
            out.append(blocks[i])
            i += 1
            continue
        group = [blocks[i]]
        expect = 2
        j = i + 1
        while j < len(blocks):
            n = _first_step_number(blocks[j])
            if n == expect:
                group.append(blocks[j])
                expect += 1
                j += 1
                continue
            # A continuation paragraph before step 2 belongs to step 1.
            if n is None and expect == 2 and j == i + 1:
                group.append(blocks[j])
                j += 1
                continue
            break
        if len(group) >= 2:
            out.append("\n\n".join(group))
            i = j
        else:
            out.append(blocks[i])
            i += 1
    return out


def _step_lines(block: str) -> int:
    return sum(1 for line in block.splitlines() if _STEP_RE.match(line.strip()))


def _is_example(block: str) -> bool:
    first = block.splitlines()[0] if block.splitlines() else ""
    if _EXAMPLE_HINT_RE.match(first.strip()):
        return True
    if "MANUAL_EXAMPLE_BLOCK" in block:
        return True
    lines = block.splitlines()
    code_hits = sum(1 for line in lines if _CODE_RE.search(line))
    return bool(lines and code_hits / len(lines) >= 0.35)


def _is_flow(block: str, section_hint: bool) -> bool:
    if section_hint:
        return True
    arrows = len(_ARROW_RE.findall(block))
    lines = block.splitlines()
    stage_lines = sum(1 for l in lines if re.match(
        r"^\s*(?:stage|phase)\s+\d+", l, re.I))
    flow_words = len(_FLOW_HINT_RE.findall(block))
    return arrows >= 2 or stage_lines >= 2 or flow_words >= 2


def _classify_section(title: str) -> bool:
    return bool(title and _FLOW_HINT_RE.search(title))


def _split_long(text: str, kind: str) -> list[str]:
    text = text.strip()
    if len(text) <= MAX_UNIT_CHARS:
        return [text] if text else []
    # Procedures/flows/examples remain coherent by paragraph first, then by
    # characters. The small overlap preserves command-line continuation context.
    parts: list[str] = []
    start = 0
    while start < len(text):
        part = text[start:start + MAX_UNIT_CHARS]
        if start + MAX_UNIT_CHARS < len(text):
            boundary = max(part.rfind("\n\n"), part.rfind("\n"), part.rfind(". "))
            if boundary > MAX_UNIT_CHARS * 0.55:
                part = part[:boundary + 1]
        if part.strip():
            parts.append(part.strip())
        start += max(len(part) - UNIT_OVERLAP_CHARS, 1)
    # A long kind can never silently degrade to prose; metadata retains it.
    return [p for p in parts if len(p) >= MIN_UNIT_CHARS or kind != "prose"]


def _section_semantic_units(body: str, section_title: str
                            ) -> list[tuple[str, str]]:
    raw_blocks = _group_step_blocks(_blocks(body))
    flow_hint = _classify_section(section_title)
    classified: list[tuple[str, str]] = []
    for block in raw_blocks:
        if "MANUAL_EXAMPLE_BLOCK" in block:
            kind = "example"
            block = block.replace("MANUAL_EXAMPLE_BLOCK\n", "").strip()
        elif _step_lines(block) >= 2 and _step_lines(block) / max(
                len(block.splitlines()), 1) >= 0.28:
            kind = "steps"
        elif _is_flow(block, flow_hint and not _is_example(block)):
            kind = "flow"
        elif _is_example(block):
            kind = "example"
        else:
            kind = "prose"
        # Keep adjacent same-kind semantic blocks together (common in PDFs).
        if classified and classified[-1][0] == kind:
            classified[-1] = (kind, classified[-1][1] + "\n\n" + block)
        else:
            classified.append((kind, block))

    # The heading-bearing prose unit is a section unit; later prose remains
    # fine-grained context. Other semantic kinds always keep their stronger kind.
    saw_section_context = False
    result: list[tuple[str, str]] = []
    for kind, text in classified:
        if kind == "prose" and not saw_section_context and section_title:
            kind = "section"
            saw_section_context = True
        for piece in _split_long(text, kind):
            result.append((kind, piece))
    return result


def _make_unit_id(doc: str, idx: int) -> str:
    return f"{doc}#{idx:05d}"


def _title_from_text(text: str, fallback: str, metadata_title: str | None = None) -> str:
    if metadata_title:
        return _clean_manual_title(metadata_title)
    for line in text.splitlines():
        s = _clean_line(line)
        if len(s) > 3 and s.lower() not in {"contents", "table of contents"}:
            return s[:140]
    return fallback


# Vendor-suite branding embedded in PDF/HTML metadata titles (e.g. the
# "Verification Continuum" suite label) is stripped so corpus units, SFT
# instructions and index metadata stay product-neutral. Functional tool
# detection is unaffected -- it matches directory paths, not document titles.
_TITLE_BRAND_RE = re.compile(
    r"Verification\s*Continuum\s*(™|\(TM\)|TM)?|Synopsys\s*(®|\(R\))?",
    re.I)


def _clean_manual_title(title: str) -> str:
    cleaned = _TITLE_BRAND_RE.sub("", title)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–—:,.|")
    return cleaned or title.strip()


def segment_text(text: str, *, product: str, doc: str, title: str,
                 source: str, fmt: str) -> list[dict]:
    """Segment one manual into chapter/section/steps/flow/example/prose units."""
    normalized, _ = _normalize_text(_strip_toc_pages(text))
    lines = normalized.splitlines()
    sections: list[tuple[str, str, int, str, list[str]]] = []
    chapter = ""
    section = ""
    heading_title = ""
    heading_level = 99
    body: list[str] = []

    def flush() -> None:
        if not (heading_title or body):
            return
        sections.append((chapter, section, heading_level, heading_title, body.copy()))

    for line in lines:
        parsed = _parse_heading(line)
        if parsed:
            flush()
            body.clear()
            level, kind, clean = parsed
            if kind == "chapter" or level == 1:
                chapter = clean
                section = ""
            else:
                section = clean
            heading_level, heading_title = level, clean
            continue
        # A heading can share a paragraph with body text after PDF extraction.
        body.append(line)
    flush()

    units: list[dict] = []
    for chap, sec, level, sec_title, sec_body_lines in sections:
        if sec_body_lines:
            body_text = "\n".join(sec_body_lines).strip()
        else:
            body_text = ""
        # Empty TOC headings do not become units. Real chapters with body keep
        # chapter context; top-level heading units are classified as chapter.
        if not body_text and level > 1:
            continue
        if not body_text and level == 1:
            # Chapter heading followed directly by a subsection has no content;
            # it is still valuable as a chapter anchor for the next section.
            body_text = sec_title
        semantic = _section_semantic_units(body_text, sec_title)
        if level == 1 and sec_title and (
                not semantic or semantic[0][0] not in {"steps", "flow", "example"}):
            semantic.insert(0, ("chapter", sec_title if not body_text else body_text))
        for kind, text_piece in semantic:
            if len(text_piece) < MIN_UNIT_CHARS and kind not in {"chapter", "section"}:
                continue
            units.append({
                "unit_id": _make_unit_id(doc, len(units)),
                "product": product,
                "doc": doc,
                "manual_title": title,
                "source": source,
                "format": fmt,
                "kind": kind,
                "chapter": chap or sec_title,
                "section": sec if sec else (sec_title if level > 1 else ""),
                "title": sec_title or chap or title,
                "text": text_piece,
                "text_sha256": hashlib.sha256(
                    text_piece.encode("utf-8", "replace")).hexdigest(),
            })
    return units


# ---------------------------------------------------------------------------
# build corpus and index
# ---------------------------------------------------------------------------


def _sft_instruction(unit: dict) -> str:
    where = f"{unit['manual_title']} ({unit['product']}/{unit['doc']})"
    place = unit["section"] or unit["chapter"] or unit["title"]
    return {
        "chapter": f"Extract the reusable technical knowledge from {place} in {where}.",
        "section": f"Explain {place} in {where}; preserve commands, options, and constraints.",
        "steps": f"Give the exact operating steps for {place} in {where}.",
        "flow": f"Describe the {place} flow in {where}, including stage inputs, outputs, and handoffs.",
        "example": f"Explain and reproduce the {place} example from {where}.",
        "prose": f"Answer technical questions using the manual excerpt for {place} in {where}.",
    }[unit["kind"]]


def generate_sft(out: Path | None = None) -> dict:
    out = _out_root(out)
    paths = _artifact_paths(out)
    layout = _UnitsLayout(out)
    if not layout.available:
        return {"error": "structured units not built; run build() first"}
    records = ({
        "instruction": _sft_instruction(u),
        "input": f"source={u['source']}; unit={u['unit_id']}; kind={u['kind']}",
        "output": u["text"],
    } for u, _off in layout.iter_with_offsets())
    sp = _sft_shard_paths(out)
    info = _write_jsonl_sharded_from_iter(records, sp["dir"], "sft")
    _write_json_atomic(sp["manifest"], {
        "format": "jsonl-shards-v1", "stem": "sft",
        "max_target_bytes": DATA_SHARD_BYTES, **info,
        "created_unix": time.time()})
    if paths["sft"].exists():
        paths["sft"].unlink()
    _invalidate_cache(out)
    return {"records": info["records"], "path": str(sp["dir"]),
            "shards": len(info["files"]), "bytes": info["total_bytes"]}


def _units_iter(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _pack_str_col(values: list) -> tuple[np.ndarray, np.ndarray]:
    """Variable-length UTF-8 column: uint8 blob + int64 row offsets."""
    enc = [str(v).encode("utf-8") for v in values]
    data = np.frombuffer(b"".join(enc), dtype=np.uint8)
    offs = np.zeros(len(enc) + 1, dtype=np.int64)
    if enc:
        np.cumsum(np.fromiter((len(e) for e in enc), dtype=np.int64,
                              count=len(enc)), out=offs[1:])
    return data, offs


def _concat_packed(parts: list) -> tuple[np.ndarray, np.ndarray]:
    """Merge per-shard packed columns into one global packed column."""
    total_rows = sum(max(len(o) - 1, 0) for _, o in parts)
    total_bytes = sum(len(d) for d, _ in parts)
    data = np.empty(total_bytes, dtype=np.uint8)
    offs = np.empty(total_rows + 1, dtype=np.int64)
    bpos = rpos = 0
    base = 0
    for d, o in parts:
        n = max(len(o) - 1, 0)
        data[bpos:bpos + len(d)] = d
        offs[rpos:rpos + n] = o[:n] + base
        bpos += len(d)
        rpos += n
        base += int(o[-1]) if len(o) else 0
    offs[-1] = base
    return data, offs


META_STR_COLS = ("unit_id", "product", "doc", "kind",
                 "chapter", "section", "title")


def _write_sharded_index(out: Path, indptr: np.ndarray, indices: np.ndarray,
                         data: np.ndarray, meta: list[dict]) -> dict:
    """Persist retrieval postings as shards strictly < 50 MiB per file.

    Search never reads the CSR row vectors (``indptr``/``indices``/``data``
    only derive postings), so each shard stores just its inverted files:
    terms/post_ptr/post_rows/post_vals.  Rows are partitioned by an nnz byte
    budget; post_rows keep GLOBAL row ids so per-shard scoring needs no offset
    remapping.  Shards are uncompressed for fast parallel loads.
    """
    sp = _shard_paths(out)
    sp["dir"].mkdir(parents=True, exist_ok=True)
    for stale in sp["dir"].glob("*"):
        if stale.is_file() and stale.name != "manifest.json":
            stale.unlink()
    n = len(meta)
    nnz_per_row = np.diff(indptr)
    meta_bytes = np.fromiter(
        (sum(len(str(m.get(k, "")).encode("utf-8")) + 1
             for k in META_STR_COLS) + 8 for m in meta),
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
        seg_row = np.repeat(
            np.arange(a, b, dtype=np.int32), nnz_per_row[a:b])
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
        for k in META_STR_COLS:
            d, o = _pack_str_col([m.get(k, "") for m in meta[a:b]])
            mcols[f"cd_{k}"] = d
            mcols[f"co_{k}"] = o
        mcols["offset"] = np.asarray(
            [m.get("_unit_offset", -1) for m in meta[a:b]], dtype=np.int64)
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
    _write_json_atomic(sp["manifest"], manifest)
    # retire legacy artifacts (monolithic + v1 npz/json shards)
    legacy = _artifact_paths(out)
    for key in ("vectors", "meta"):
        if legacy[key].exists():
            legacy[key].unlink()
    for old in list(sp["dir"].glob("shard_*.npz")) + list(sp["dir"].glob("meta_*.json")):
        old.unlink()
    return {"shards": len(shards), "max_file_bytes": max_file_bytes}


def build_index(out: Path | None = None) -> dict:
    out = _out_root(out)
    paths = _artifact_paths(out)
    if not paths["units"].exists() and not _units_shard_paths(out)["manifest"].exists():
        return {"error": "structured units not built; run build() first"}
    t0 = time.time()
    rows: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    meta: list[dict] = []
    df = np.zeros(DIM, dtype=np.float64)
    layout = _UnitsLayout(out)
    if not layout.available:
        return {"error": "structured units not found (monolithic or shards)"}
    for unit, offset in layout.iter_with_offsets():
        indexed_text = " ".join((
            unit["product"], unit["doc"], unit["manual_title"],
            unit["chapter"], unit["section"], unit["title"],
            unit["kind"], unit["text"],
        ))
        toks = _tokens(indexed_text)
        if toks:
            hashes = np.asarray([_hash(t) for t in toks], dtype=np.int64)
            unique, count = np.unique(hashes, return_counts=True)
            rows.append(unique)
            vals.append(count.astype(np.float32))
            df[unique] += 1.0
            meta.append({**{k: unit[k] for k in (
                "unit_id", "product", "doc", "kind", "chapter",
                "section", "title"
            )}, "_unit_offset": offset})
    n = len(meta)
    if not n:
        return {"error": "no indexable structured units"}
    idf = np.log((n + 1.0) / (df + 1.0)) + 1.0
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum([len(r) for r in rows], out=indptr[1:])
    indices = np.concatenate(rows)
    values = (1.0 + np.log(np.concatenate(vals))) * idf[indices]
    data = values.astype(np.float32)
    for i in range(n):
        seg = data[indptr[i]:indptr[i + 1]]
        seg /= np.linalg.norm(seg) or 1.0
    sharding = _write_sharded_index(out, indptr, indices, data, meta)
    _invalidate_cache(out)
    return {
        "units": n,
        "docs": len({(m["product"], m["doc"]) for m in meta}),
        "dim": DIM,
        "index_dir": str(_shard_paths(out)["dir"]),
        **sharding,
        "build_seconds": round(time.time() - t0, 2),
    }


_CACHE: tuple[Path, dict] | None = None


class _MetaCols:
    """Columnar meta view (v2): packed UTF-8 + plain numeric columns.

    ``cols`` maps name -> (uint8 blob, int64 offsets) for packed string
    columns, or -> plain ndarray for numeric columns.  ``internal`` names are
    hidden from :meth:`row` unless ``include_internal`` (e.g. manual byte
    offsets); other numeric columns (e.g. UG chunk ids) stay visible.
    """

    __slots__ = ("cols", "n", "internal")

    def __init__(self, cols: dict, internal: tuple = ("offset",)):
        self.cols = cols
        first = next(iter(cols.values()))
        if isinstance(first, tuple):      # packed column: offs has n + 1
            self.n = max(len(first[1]) - 1, 0)
        else:
            self.n = len(first)
        self.internal = tuple(internal)

    def __len__(self) -> int:
        return self.n

    def get(self, i: int, name: str) -> str:
        c = self.cols[name]
        if isinstance(c, tuple):
            d, o = c
            return bytes(d[o[i]:o[i + 1]]).decode("utf-8")
        v = c[i]
        return v.item() if hasattr(v, "item") else v

    def eq_mask(self, name: str, value, rows: np.ndarray) -> np.ndarray:
        """Boolean mask over ``rows`` where column ``name`` equals value."""
        vb = str(value).encode("utf-8")
        d, o = self.cols[name]
        starts = o[rows]
        ends = o[rows + 1]
        mask = (ends - starts) == len(vb)
        for j in np.flatnonzero(mask):
            if bytes(d[starts[j]:ends[j]]) != vb:
                mask[j] = False
        return mask

    def row(self, i: int, include_internal: bool = False) -> dict:
        r = {name: self.get(i, name) for name in self.cols
             if name not in self.internal}
        if include_internal:
            r["_unit_offset"] = int(self.cols["offset"][i])
        return r


def _invalidate_cache(root: Path | None = None) -> None:
    """Drop the in-process index cache after any artifact rewrite."""
    global _CACHE
    if root is None or (_CACHE is not None and _CACHE[0] == _out_root(root)):
        _CACHE = None


def _load_index(out: Path | None = None):
    global _CACHE
    root = _out_root(out)
    if _CACHE is not None and _CACHE[0] == root:
        return _CACHE[1]
    paths = _artifact_paths(root)
    if not paths["units"].exists() and not _units_shard_paths(root)["manifest"].exists():
        return None
    sp = _shard_paths(root)
    if sp["manifest"].exists():
        sm = json.loads(sp["manifest"].read_text(encoding="utf-8"))
        if sm.get("format") == "sharded-postings-v2":
            shard_arrays = []
            col_lists: dict[str, list] = {k: [] for k in (
                "unit_id", "product", "doc", "kind", "chapter",
                "section", "title", "offset")}
            for s in sm["shards"]:
                shard_arrays.append({k: np.load(
                    sp["dir"] / s[k], mmap_mode="r")
                    for k in ("terms", "post_ptr", "post_rows", "post_vals")})
                mz = np.load(sp["dir"] / s["meta"])
                for k in META_STR_COLS:
                    col_lists[k].append((mz[f"cd_{k}"], mz[f"co_{k}"]))
                col_lists["offset"].append(mz["offset"])
                mz.close()
            arrays = {"shards": shard_arrays, "n_rows": sm["n_rows"], "v2": True}
            meta = _MetaCols({**{k: _concat_packed(v)
                                 for k, v in col_lists.items()
                                 if k != "offset"},
                              "offset": np.concatenate(col_lists["offset"])})
        else:
            from concurrent.futures import ThreadPoolExecutor
            files = [sp["dir"] / s["npz"] for s in sm["shards"]]

            def _load_one(p: Path) -> dict:
                z = np.load(p)
                arrs = {k: z[k] for k in ("terms", "post_ptr", "post_rows", "post_vals")}
                z.close()
                return arrs

            with ThreadPoolExecutor(max_workers=4) as ex:
                shard_arrays = list(ex.map(_load_one, files))
            arrays = {"shards": shard_arrays, "n_rows": sm["n_rows"]}
            metas = [json.loads((sp["dir"] / s["meta"]).read_text(encoding="utf-8"))
                     for s in sm["shards"]]
            meta = [m for part in metas for m in part]
    elif paths["vectors"].exists() and paths["meta"].exists():
        loaded = np.load(paths["vectors"])
        arrays = {k: loaded[k] for k in (
            "terms", "post_ptr", "post_rows", "post_vals")}
        loaded.close()
        meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    else:
        return None
    # Lazy units: when shard metas carry byte offsets we skip parsing the
    # multi-hundred-MB units file at load time and seek per hit instead.
    has_offsets = (isinstance(meta, _MetaCols) and (meta.cols["offset"] >= 0).all()) or \
                  (isinstance(meta, list) and meta and all("_unit_offset" in m for m in meta))
    if "shards" in arrays and has_offsets:
        units = _UnitsLayout(root)      # byte-addressable sharded view
    else:
        layout = _UnitsLayout(root)
        units = ({u["unit_id"]: u for u, _ in layout.iter_with_offsets()}
                 if layout.available else {})
    result = (arrays, meta, units)
    _CACHE = (root, result)
    return result


def search(query: str, product: str | None = None, doc: str | None = None,
           kind: str | None = None, top_k: int = 5,
           out: Path | None = None, max_text: int = 4000) -> dict:
    loaded = _load_index(out)
    if loaded is None:
        return {"error": "manual corpus not built; run manual_ingest build first"}
    arrays, meta, units = loaded
    toks = _tokens(query)
    if not toks:
        return {"error": "empty query"}
    hashes = [ _hash(t) for t in toks ]
    q_counts = Counter(hashes)
    scores = np.zeros(len(meta), dtype=np.float64)
    if "shards" in arrays:
        hit_rows: list[np.ndarray] = []
        hit_vals: list[np.ndarray] = []
        for shard in arrays["shards"]:
            terms = shard["terms"]
            post_ptr = shard["post_ptr"]
            post_rows = shard["post_rows"]
            post_vals = shard["post_vals"]
            for term, q_tf in q_counts.items():
                pos = int(np.searchsorted(terms, term))
                if pos >= len(terms) or int(terms[pos]) != term:
                    continue
                s, e = int(post_ptr[pos]), int(post_ptr[pos + 1])
                hit_rows.append(post_rows[s:e])
                hit_vals.append(post_vals[s:e].astype(np.float64) * q_tf)
        if hit_rows:
            scores = np.bincount(np.concatenate(hit_rows),
                                 weights=np.concatenate(hit_vals),
                                 minlength=len(meta))
    else:
        terms = arrays["terms"]
        post_ptr = arrays["post_ptr"]
        post_rows = arrays["post_rows"]
        post_vals = arrays["post_vals"]
        for term, q_tf in q_counts.items():
            pos = int(np.searchsorted(terms, term))
            if pos >= len(terms) or int(terms[pos]) != term:
                continue
            s, e = int(post_ptr[pos]), int(post_ptr[pos + 1])
            np.add.at(scores, post_rows[s:e], post_vals[s:e].astype(np.float64) * q_tf)
    qnorm = math.sqrt(sum(v * v for v in q_counts.values())) or 1.0
    scores /= qnorm
    hits: list[dict] = []
    seen_fingerprints: set[tuple[str, str]] = set()
    if isinstance(meta, _MetaCols):
        # v2: vectorized candidate filtering + bounded top-k preselection
        cand = np.flatnonzero(scores > 0)
        if product:
            cand = cand[meta.eq_mask("product", product, cand)]
        if doc:
            cand = cand[meta.eq_mask("doc", doc, cand)]
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
    for idx in order:
        if scores[idx] <= 0:
            break
        m = (meta.row(int(idx)) if isinstance(meta, _MetaCols)
             else meta[int(idx)])
        if not isinstance(meta, _MetaCols):
            if product and m["product"] != product:
                continue
            if doc and m["doc"] != doc:
                continue
            if kind and m["kind"] != kind:
                continue
        if isinstance(units, _UnitsLayout):
            off = (int(meta.cols["offset"][idx]) if isinstance(meta, _MetaCols)
                   else m["_unit_offset"])
            unit = units.read_at(off)
        else:
            unit = units[m["unit_id"]]
        text = unit["text"]
        # suppress sliding-window near-duplicates: one hit per
        # (doc, normalized prefix); keep the highest-scored chunk
        fingerprint_key = (
            m["doc"],
            re.sub(r"\s+", " ", text[:200]).strip().lower()[:120],
        )
        if fingerprint_key in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint_key)
        if len(hits) >= top_k:
            break
        hits.append({
            **{k: v for k, v in m.items() if not k.startswith("_")},
            "score": round(float(scores[idx]), 4),
            "source": unit["source"],
            "format": unit["format"],
            "text": text if len(text) <= max_text else text[:max_text],
            "text_truncated": len(text) > max_text,
        })
    return {"query": query, "hits": hits}


def _artifact_manifest(out: Path) -> dict:
    artifacts = []
    for key, path in _artifact_paths(out).items():
        if path.exists() and key != "manifest":
            artifacts.append((f"{key}:{path.name}", path))
    return {key: {"bytes": p.stat().st_size, "sha256": _sha256(p)}
            for key, p in artifacts}


def build(root: Path | None = None, out: Path | None = None,
          include_sft: bool = True) -> dict:
    """Scan -> extract -> classify -> segment -> SFT/vector-index in one pass."""
    scan_rt = _scan_root(root)
    out = _out_root(out)
    out.mkdir(parents=True, exist_ok=True)
    scanned = scan(scan_rt)
    inventory: list[dict] = []
    all_units: list[dict] = []
    accepted = rejected = failed = 0
    for item in scanned["candidates"]:
        path = Path(item["path"])
        candidate = Candidate(path, item["format"], item["bytes"])
        try:
            text, extract_info = _load_or_extract_text(candidate, scan_rt, out)
            normalized, norm_pages = _normalize_text(_strip_toc_pages(text))
            score, reason = _technical_score(normalized, candidate)
            entry = {
                **item,
                "accepted": score > 0,
                "technical_score": score,
                "reason": reason,
                "text_chars": len(normalized),
                **{k: v for k, v in extract_info.items() if k != "text_cache"},
            }
            if score <= 0:
                rejected += 1
                inventory.append(entry)
                continue
            product = _product(path, scan_rt)
            doc = _doc_name(path)
            title = _title_from_text(
                normalized,
                re.sub(r"[_]+", " ", path.stem).strip().title(),
                extract_info.get("metadata_title"),
            )
            units = segment_text(
                text, product=product, doc=doc, title=title,
                source=str(path), fmt=candidate.fmt,
            )
            if not units:
                units = [{
                    "unit_id": _make_unit_id(doc, 0), "product": product,
                    "doc": doc, "manual_title": title, "source": str(path),
                    "format": candidate.fmt, "kind": "section", "chapter": "",
                    "section": title, "title": title,
                    "text": normalized[:MAX_UNIT_CHARS],
                    "text_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
                }]
            all_units.extend(units)
            entry.update({"units": len(units), "product": product, "doc": doc,
                          "title": title})
            accepted += 1
        except Exception as exc:      # preserve the full-scan contract
            failed += 1
            inventory.append({
                **item, "accepted": False, "technical_score": 0,
                "reason": f"extraction failed: {exc}",
            })
    paths = _artifact_paths(out)
    _write_json_atomic(paths["inventory"], {
        "scan_root": str(scan_rt),
        "generated_at_unix": time.time(),
        "scanned": len(scanned["candidates"]),
        "accepted": accepted,
        "rejected": rejected,
        "failed": failed,
        "scan_errors": scanned["errors"],
        "files": inventory,
    })
    usp = _units_shard_paths(out)
    uinfo = _write_jsonl_sharded_from_iter(all_units, usp["dir"], "units")
    _write_json_atomic(usp["manifest"], {
        "format": "jsonl-shards-v1", "stem": "units",
        "max_target_bytes": DATA_SHARD_BYTES, **uinfo,
        "created_unix": time.time()})
    if paths["units"].exists():
        paths["units"].unlink()
    sft = generate_sft(out) if include_sft else {"records": 0}
    index = build_index(out)
    kind_counts = Counter(u["kind"] for u in all_units)
    product_docs = sorted({(u["product"], u["doc"]) for u in all_units})
    manifest = {
        "version": 1,
        "scan_root": str(scan_rt),
        "scanned": len(scanned["candidates"]),
        "accepted_manuals": accepted,
        "rejected_candidates": rejected,
        "failed": failed,
        "structured_units": len(all_units),
        "units_by_kind": {k: kind_counts.get(k, 0) for k in KINDS},
        "manuals_by_product": dict(sorted(Counter(p for p, _ in product_docs).items())),
        "model_sft_records": sft.get("records", 0),
        "segmentation": "chapter/section + operating steps + flow + example",
        "artifacts": _artifact_manifest(out),
    }
    _write_json_atomic(paths["manifest"], manifest)
    return manifest


def status(out: Path | None = None) -> dict:
    out = _out_root(out)
    paths = _artifact_paths(out)
    if not paths["manifest"].exists():
        return {"built": False, "corpus_root": str(out)}
    result = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    result["built"] = True
    result["corpus_root"] = str(out)
    return result


def __main__() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("op", choices=("scan", "build", "sft", "search", "status"))
    parser.add_argument("query", nargs="*", default=[])
    parser.add_argument("--root", help="recursive PDF/HTML scan root")
    parser.add_argument("--out", help="corpus output root")
    parser.add_argument("--product")
    parser.add_argument("--doc")
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.op == "scan":
        result = scan(args.root)
    elif args.op == "build":
        result = build(args.root, args.out)
    elif args.op == "sft":
        result = generate_sft(args.out)
    elif args.op == "search":
        result = search(" ".join(args.query), product=args.product, doc=args.doc,
                        kind=args.kind, top_k=args.top_k, out=args.out)
    else:
        result = status(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    __main__()
