"""Synopsys NPI (Native Programming Interface) API 索引与查询.

解析 NPI/inc 下 24 个 C/C++ 头文件, 建立 484 个 npi_* API 的
family(头文件模块)/签名/声明索引, 供 AI agent 按 family 浏览或按
关键词检索 (FSDB 波形 / 覆盖率 / UPF / VCS / NL / SDB ...).

纯标准库实现; 环境变量 CHIP_AGENT_NPI_INC 覆盖头文件目录.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .site_paths import NPI_INC as NPI_INC_DEFAULT

# header file stem -> human-readable family description
FAMILY_DESC = {
    "npi": "NPI core: init/exit, object model, common callbacks",
    "npi_type": "基础类型/枚举/常量 (NPI_BOOL, npiReturn, ...)",
    "npi_dm": "Design Manager: 设计数据库读取 (最大模块, 3038 行)",
    "npi_hdl": "HDL 对象模型: instance/net/port/reg 迭代与属性",
    "npi_fsdb": "FSDB 读取: file/scope/signal 属性与值迭代",
    "npi_fsdbw": "FSDB 写 (dump 控制)",
    "npi_fsdb_trans": "FSDB transaction 数据读取",
    "npi_fsdbw_trans": "FSDB transaction 写",
    "npi_cov": "覆盖率数据库 (UCDB) 读取",
    "npi_cv": "Coverage 细节: bin/hit/cross 细粒度数据",
    "npi_vcs": "VCS 仿真引擎接口",
    "npi_upf": "UPF 低功耗意图读取",
    "npi_nl": "Netlist 后端接口",
    "npi_pw": "Power-aware 接口",
    "npi_hvp": "Hybrid Verification Platform 接口",
    "npi_pst": "Power State Table 操作",
    "npi_sdb": "SDB 数据库接口",
    "npi_ltr": "LTR (lint/trace) 接口",
    "npi_util": "通用工具 (内存/字符串)",
    "npi_text": "文本处理接口",
    "npi_ic": "Interconnect 接口",
    "npi_ee": "EE 接口",
    "verdilearn": "VerdiLearn: msgdb/vLLM 消息数据库接口",
}

_DECL_RE = re.compile(
    r"(?m)^[^\n;{}]*?\b(npi_[A-Za-z0-9_]+|npi[A-Z][A-Za-z0-9_]+)\s*\([^;{]*?\)\s*;",
    re.S,
)

# in-process parse cache keyed by include dir (MCP server lifetime);
# 24 headers / ~5k lines re-scanned per call otherwise (~12ms each).
_API_CACHE: dict[str, list[dict]] = {}

# Transformed corpus path (query-time reads ONLY from this file, never .h sources)
CORPUS_PATH = Path(__file__).parent / "corpus" / "npi" / "npi_corpus.json"


def _load_corpus() -> list[dict] | None:
    """Load pre-built NPI corpus (JSON) — no source .h reads at query time."""
    if CORPUS_PATH.exists():
        try:
            return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def build_corpus(out: Path | None = None) -> dict:
    """One-time build: parse .h files → JSON corpus. Call at build/deploy time."""
    out = out or CORPUS_PATH
    inc = _inc_dir()
    if not inc.is_dir():
        return {"error": f"NPI include dir not found: {inc}"}
    out.parent.mkdir(parents=True, exist_ok=True)
    api = _parse_api_from_source(inc)
    # Also cache header file list (avoids glob at query time)
    headers = sorted(h.name for h in inc.glob("*.h"))
    out.write_text(json.dumps({
        "api": api, "headers": headers, "inc": str(inc),
        "built_at": __import__("time").time(),
    }, ensure_ascii=False), encoding="utf-8")
    return {"apis": len(api), "headers": len(headers), "corpus": str(out)}


def _parse_api_from_source(inc: Path) -> list[dict]:
    """Parse .h files (build time only)."""
    out: dict[str, dict] = {}
    for h in sorted(inc.glob("*.h")):
        text = h.read_text(errors="replace")
        family = _family_of(h.name)
        for m in _DECL_RE.finditer(text):
            name = m.group(1)
            if name in out:
                continue
            decl = " ".join(m.group(0).split())
            line = text.count("\n", 0, m.start()) + 1
            out[name] = {
                "name": name, "family": family, "header": h.name,
                "decl": decl[:400], "line": line,
            }
    return sorted(out.values(), key=lambda a: (a["family"], a["name"]))


def _inc_dir() -> Path:
    return Path(os.environ.get("CHIP_AGENT_NPI_INC", NPI_INC_DEFAULT))


def _family_of(header: str) -> str:
    stem = Path(header).stem
    if stem.startswith("npi_fsdbw_trans"):
        return "npi_fsdbw_trans"
    if stem.startswith("npi_fsdbw"):
        return "npi_fsdbw"
    if stem.startswith("npi_fsdb_trans"):
        return "npi_fsdb_trans"
    if stem.startswith("npi_fsdb"):
        return "npi_fsdb"
    return stem


def _parse_api(inc: Path) -> list[dict]:
    """Load API index from transformed corpus (query time: NO .h source reads).

    Falls back to one-time build from source if corpus file is missing.
    """
    key = str(inc)
    cached = _API_CACHE.get(key)
    if cached is not None:
        return cached

    # 1. Try pre-built corpus
    corpus = _load_corpus()
    if corpus and isinstance(corpus.get("api"), list):
        api = corpus["api"]
        _API_CACHE[key] = api
        return api

    # 2. One-time build from source (build time, not steady-state query)
    api = _parse_api_from_source(inc)
    try:
        build_corpus()
    except Exception:
        pass  # best-effort: still cache in memory even if disk write fails
    _API_CACHE[key] = api
    return api


def families() -> dict:
    inc = _inc_dir()
    api = _parse_api(inc)
    by_fam: dict[str, int] = {}
    for a in api:
        by_fam[a["family"]] = by_fam.get(a["family"], 0) + 1
    # Get header count from corpus (avoid .h glob at query time)
    corpus = _load_corpus()
    n_headers = len(corpus.get("headers", [])) if corpus else len(by_fam)
    return {
        "inc": str(inc),
        "headers": n_headers,
        "apis": len(api),
        "families": dict(sorted(by_fam.items(),
                                key=lambda kv: -kv[1])),
        "family_desc": {k: v for k, v in FAMILY_DESC.items()
                        if k in by_fam},
        "family_notes": {
            # verdilearn.h 用非 npi_ 前缀命名 (VL_* / VerdiLearn_* 等),
            # _DECL_RE 按 npi_ 前缀解析, 故此家族 API 计数为 0; 接口
            # 仍可通过 search(keyword) 在头文件文本中命中声明片段.
            "verdilearn": "0 API: 头文件使用非 npi_ 前缀命名, "
                          "当前解析规则仅匹配 npi_* 声明",
        } if by_fam.get("verdilearn", 0) == 0 else {},
    }


def search(keyword: str, family: str | None = None, top_k: int = 20) -> dict:
    inc = _inc_dir()
    api = _parse_api(inc)
    kw = keyword.lower()
    hits = [a for a in _parse_api(inc)
            if (kw in a["name"].lower() or kw in a["decl"].lower())
            and (family is None or a["family"] == family)]
    return {"keyword": keyword, "count": len(hits),
            "hits": hits[: max(1, min(100, top_k))]}


def get(name: str) -> dict:
    inc = _inc_dir()
    for a in _parse_api(inc):
        if a["name"] == name:
            return a
    return {"error": f"NPI API not found: {name}"}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NPI API index")
    ap.add_argument("op", choices=["families", "search", "get"])
    ap.add_argument("arg", nargs="?", default="")
    ap.add_argument("--family")
    a = ap.parse_args()
    if a.op == "families":
        print(json.dumps(families(), ensure_ascii=False, indent=2))
    elif a.op == "search":
        print(json.dumps(search(a.arg, family=a.family), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(get(a.arg), ensure_ascii=False, indent=2))
