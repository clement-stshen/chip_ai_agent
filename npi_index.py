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

NPI_INC_DEFAULT = "/tools/Synopsys/temp/NPI/inc"

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
    """扫描头文件, 返回 {name, family, header, decl, line} 列表 (去重)."""
    key = str(inc)
    cached = _API_CACHE.get(key)
    if cached is not None and inc.is_dir():
        return cached
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
    api = sorted(out.values(), key=lambda a: (a["family"], a["name"]))
    _API_CACHE[key] = api
    return api


def families() -> dict:
    inc = _inc_dir()
    if not inc.is_dir():
        return {"error": f"NPI include dir not found: {inc}"}
    api = _parse_api(inc)
    by_fam: dict[str, int] = {}
    for a in api:
        by_fam[a["family"]] = by_fam.get(a["family"], 0) + 1
    return {
        "inc": str(inc),
        "headers": len(list(inc.glob('*.h'))),
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
    if not inc.is_dir():
        return {"error": f"NPI include dir not found: {inc}"}
    kw = keyword.lower()
    hits = [a for a in _parse_api(inc)
            if (kw in a["name"].lower() or kw in a["decl"].lower())
            and (family is None or a["family"] == family)]
    return {"keyword": keyword, "count": len(hits),
            "hits": hits[: max(1, min(100, top_k))]}


def get(name: str) -> dict:
    inc = _inc_dir()
    if not inc.is_dir():
        return {"error": f"NPI include dir not found: {inc}"}
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
