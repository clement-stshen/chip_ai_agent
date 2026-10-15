"""Golden TB 范例库索引 (Verification Academy uart_example 等).

纯标准库; 扫描范例根目录, 按路径归类 (rtl/agent/uvm_tb/sim/...),
支持按文件名/内容检索, 供 generate_testbench / generate_uvm_env
recipe 引用黄金结构. 环境变量 CHIP_AGENT_EXAMPLES 覆盖根目录.
"""

from __future__ import annotations

import os
from pathlib import Path

EXAMPLES_DEFAULT = "/tools/Synopsys/temp/uart_example"

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
    if cached is not None and root.is_dir():
        return cached
    out = []
    if not root.is_dir():
        return root, out
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.stat().st_size < 1_000_000:
            rel = str(f.relative_to(root))
            out.append({"path": rel, "category": _categorize(rel),
                        "bytes": f.stat().st_size})
    _SCAN_CACHE[key] = (root, out)
    return root, out


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
    if not root.is_dir():
        return {"error": f"examples root not found: {root}"}
    kw = keyword.lower()
    name_hits = []
    content_hits = []
    for f in files:
        if category and f["category"] != category:
            continue
        if kw in f["path"].lower():
            name_hits.append(f)
            continue
        p = root / f["path"]
        try:
            if p.suffix in (".sv", ".svh", ".v", ".vh", ".py", ".mk",
                            ".tcl", ".f", ".md") and \
                    kw in p.read_text(errors="replace").lower():
                content_hits.append(f)
        except OSError:
            continue
    hits = name_hits + content_hits
    return {"keyword": keyword, "count": len(hits),
            "hits": hits[: max(1, min(100, top_k))]}


def get(rel_path: str, max_bytes: int = 8000) -> dict:
    root, _ = _scan()
    p = (root / rel_path).resolve()
    if not str(p).startswith(str(root.resolve())) or not p.is_file():
        return {"error": f"not found under examples root: {rel_path}"}
    try:
        text = p.read_text(errors="replace")[:max_bytes]
    except OSError as e:
        return {"error": f"unreadable: {e}"}
    return {"path": rel_path, "category": _categorize(rel_path),
            "truncated": p.stat().st_size > max_bytes, "content": text}


if __name__ == "__main__":
    import argparse
    import json
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
