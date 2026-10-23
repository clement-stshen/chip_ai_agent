"""Golden TB 范例库索引 (Verification Academy uart_example 等).

纯标准库; 扫描范例根目录, 按路径归类 (rtl/agent/uvm_tb/sim/...),
支持按文件名/内容检索, 供 generate_testbench / generate_uvm_env
recipe 引用黄金结构. 环境变量 CHIP_AGENT_EXAMPLES 覆盖根目录.
"""

from __future__ import annotations

import json

import os
from pathlib import Path

from .site_paths import UART_EXAMPLE as EXAMPLES_DEFAULT

# path keyword -> category
CATEGORY_RULES = [
    ("/rtl", "rtl"),
    ("/agents/", "uvm_agent"),
    ("/uvm_tb/env", "uvm_env"),
    ("/uvm_tb/tests", "uvm_test"),
    ("/uvm_tb/sequences", "uvm_sequence"),
    ("/uvm_tb/virtual_sequences", "uvm_vsequence"),
    ("/uvm_tb/register_model", "uvm_regmodel"),
    ("/uvm_tb/tb", "uvm_tb_top"),
    ("/protocol_monitor", "protocol_monitor"),
    ("/sim", "sim_script"),
    ("/docs", "docs"),
]

# in-process scan cache keyed by resolved root path (MCP server lifetime);
# dropped when the env var changes or the root disappears.
_SCAN_CACHE: dict[str, tuple[Path, list[dict]]] = {}

# Transformed corpus (query-time reads ONLY from this file, never source .sv/.svh)
CORPUS_PATH = Path(__file__).parent / "corpus" / "examples" / "examples_corpus.json"
# Content index: path → {content: first 8KB, category, bytes}
_CONTENT_INDEX: dict[str, dict] = {}


def _load_corpus() -> dict | None:
    if CORPUS_PATH.exists():
        try:
            return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def build_corpus(out: Path | None = None) -> dict:
    """One-time build: scan examples → JSON corpus with indexed content."""
    out = out or CORPUS_PATH
    root = _root()
    if not root.is_dir():
        return {"error": f"examples root not found: {root}"}
    out.parent.mkdir(parents=True, exist_ok=True)
    files = []
    content_map = {}
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.stat().st_size >= 1_000_000:
            continue
        rel = str(f.relative_to(root))
        entry = {"path": rel, "category": _categorize(rel),
                 "bytes": f.stat().st_size}
        files.append(entry)
        # Pre-index content for text search (first 8KB, enough for pattern match)
        if f.suffix in (".sv", ".svh", ".v", ".vh", ".py", ".mk", ".tcl", ".f", ".md"):
            try:
                content_map[rel] = f.read_text(errors="replace")[:8000].lower()
            except OSError:
                pass
    out.write_text(json.dumps({
        "files": files, "content_index": content_map, "root": str(root),
    }, ensure_ascii=False), encoding="utf-8")
    return {"files": len(files), "indexed_content": len(content_map),
            "corpus": str(out)}


def _root() -> Path:
    return Path(os.environ.get("CHIP_AGENT_EXAMPLES", EXAMPLES_DEFAULT))


def _categorize(rel: str) -> str:
    low = "/" + rel.lower()
    for pat, cat in CATEGORY_RULES:
        if pat in low:
            return cat
    return "other"


def _scan():
    root = _root()
    key = str(root)
    cached = _SCAN_CACHE.get(key)
    if cached is not None:
        return cached

    # 1. Try pre-built corpus (NO source file reads at query time)
    corpus = _load_corpus()
    if corpus and isinstance(corpus.get("files"), list):
        out = corpus["files"]
        _CONTENT_INDEX.clear()
        _CONTENT_INDEX.update(corpus.get("content_index", {}))
        result = (Path(corpus.get("root", str(root))), out)
        _SCAN_CACHE[key] = result
        return result

    # 2. One-time build from source (build time only)
    out = []
    content_idx = {}
    if root.is_dir():
        for f in sorted(root.rglob("*")):
            if f.is_file() and f.stat().st_size < 1_000_000:
                rel = str(f.relative_to(root))
                out.append({"path": rel, "category": _categorize(rel),
                            "bytes": f.stat().st_size})
                if f.suffix in (".sv", ".svh", ".v", ".vh", ".py", ".mk",
                                ".tcl", ".f", ".md"):
                    try:
                        content_idx[rel] = f.read_text(errors="replace")[:8000].lower()
                    except OSError:
                        pass
    # Persist corpus for future queries
    try:
        build_corpus()
    except Exception:
        pass
    _CONTENT_INDEX.clear()
    _CONTENT_INDEX.update(content_idx)
    result = (root, out)
    _SCAN_CACHE[key] = result
    return result


def list_files(category: str | None = None) -> dict:
    root, files = _scan()
    if not files and not root.is_dir():
        return {"error": f"examples root not found: {root}"}
    cats: dict[str, int] = {}
    for f in files:
        cats[f["category"]] = cats.get(f["category"], 0) + 1
    hits = files if category is None else \
        [f for f in files if f["category"] == category]
    return {"root": str(root), "total": len(files), "by_category": cats,
            "category": category, "files": hits[:200]}


def search(keyword: str, category: str | None = None,
           top_k: int = 20) -> dict:
    root, files = _scan()
    kw = keyword.lower()
    name_hits = []
    content_hits = []
    for f in files:
        if category and f["category"] != category:
            continue
        if kw in f["path"].lower():
            name_hits.append(f)
            continue
        # Read from pre-indexed content (NO source file reads at query time)
        content = _CONTENT_INDEX.get(f["path"], "")
        if content and kw in content:
            content_hits.append(f)
    hits = name_hits + content_hits
    return {"keyword": keyword, "count": len(hits),
            "hits": hits[: max(1, min(100, top_k))]}


def get(rel_path: str, max_bytes: int = 8000) -> dict:
    root, _ = _scan()
    # Read from pre-indexed content cache (corpus), not source files
    content = _CONTENT_INDEX.get(rel_path, "")
    if content:
        return {"path": rel_path, "category": _categorize(rel_path),
                "truncated": len(content) >= max_bytes,
                "content": content[:max_bytes]}
    # Fallback: check if file exists in scan results (metadata only)
    _, files = _scan()
    meta = next((f for f in files if f["path"] == rel_path), None)
    if meta is None:
        return {"error": f"not found under examples root: {rel_path}"}
    return {"path": rel_path, "category": meta.get("category", "other"),
            "truncated": False, "content": "(content not indexed; run build_corpus())"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="golden TB examples index")
    ap.add_argument("op", choices=["list", "search", "get"])
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--category")
    a = ap.parse_args()
    if a.op == "list":
        print(json.dumps(list_files(a.category or None), indent=2))
    elif a.op == "search":
        print(json.dumps(search(a.arg, category=a.category), indent=2))
    else:
        print(json.dumps(get(a.arg), indent=2))
