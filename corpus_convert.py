"""Convert DeepSeek-exported HTML corpus pages into SFT training files.

Supported output formats (mirroring the source page's download buttons):
  * pcie_ovm_sft.jsonl      - one Alpaca record per line (Unsloth / LLaMA-Factory)
  * pcie_ovm_sft.json       - JSON array of the same records
  * pcie_ovm_alpaca.json    - Alpaca {"instruction","input","output"} list
  * pcie_ovm_sharegpt.json  - ShareGPT conversations list

The exporter pages embed a JavaScript ``const CORPUS = [...]`` array.  Some
exports are truncated mid-record, so the parser is lenient: it recovers the
JSON-escaped string literals per record and closes the trailing record.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _read_html(path: Path) -> str:
    from bs4 import BeautifulSoup  # installed via pip (bs4 + lxml)

    soup = BeautifulSoup(path.read_bytes(), "lxml")
    title = soup.title.string if soup.title else ""
    # JS string literals survive the soup round-trip inside <script>
    scripts = "\n".join(s.get_text() for s in soup.find_all("script"))
    return f"<!-- {title or ''} -->\n{scripts}"


def _extract_js_strings(record_src: str) -> dict | None:
    """Parse the instruction/input/output string literals of one record.

    A truncated (unterminated) trailing ``output`` literal is closed
    implicitly; records without a usable instruction+output are dropped.
    """
    out: dict = {}
    for key in ("instruction", "input", "output"):
        m = re.search(rf'{key}\s*:\s*"', record_src)
        if not m:
            out[key] = ""
            continue
        i = m.end()
        buf: list[str] = []
        while i < len(record_src):
            ch = record_src[i]
            if ch == "\\" and i + 1 < len(record_src):
                nxt = record_src[i + 1]
                if nxt == "n":
                    buf.append("\n")
                elif nxt == "t":
                    buf.append("\t")
                elif nxt == "u" and i + 5 < len(record_src):
                    buf.append(chr(int(record_src[i + 2:i + 6], 16)))
                    i += 4
                else:                      # \" \\ \/ and unknown escapes
                    buf.append(nxt)
                i += 2
                continue
            if ch == '"':
                break                      # properly closed literal
            buf.append(ch)
            i += 1
        # loop end without a closing quote => truncated export; keep text
        out[key] = "".join(buf).strip()
    if not out.get("instruction") or not out.get("output"):
        return None
    out.setdefault("input", "")
    return out


def parse_corpus(html_path: str | Path) -> list[dict]:
    """Extract every Alpaca record embedded in the HTML export."""
    text = _read_html(Path(html_path))
    m = re.search(r"const\s+CORPUS\s*=\s*\[", text)
    if not m:
        return []
    body = text[m.end():]
    records: list[dict] = []
    starts = [mm.start() for mm in
              re.finditer(r"\{\s*\n?\s*instruction\s*:", body)]
    for idx, s in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(body)
        rec = _extract_js_strings(body[s:end])
        if rec:
            records.append(rec)
    return records


def to_sharegpt(records: list[dict]) -> list[dict]:
    convs = []
    for r in records:
        user = r["instruction"] + (f"\n\n{r['input']}" if r.get("input") else "")
        convs.append({"conversations": [
            {"from": "human", "value": user},
            {"from": "gpt", "value": r["output"]},
        ]})
    return convs


def convert(html_path: str | Path, out_dir: str | Path,
            prefix: str = "pcie_ovm") -> dict:
    """Parse the HTML and write all four SFT corpus formats."""
    records = parse_corpus(html_path)
    if not records:
        return {"error": "no corpus records parsed"}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / f"{prefix}_sft.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out / f"{prefix}_sft.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{prefix}_alpaca.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{prefix}_sharegpt.json").write_text(
        json.dumps(to_sharegpt(records), ensure_ascii=False, indent=2),
        encoding="utf-8")
    # validate: every JSONL line must parse back
    n_ok = 0
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            json.loads(line)
            n_ok += 1
    return {
        "ok": True,
        "records": len(records),
        "jsonl_lines_validated": n_ok,
        "outputs": sorted(p.name for p in out.glob(f"{prefix}_*")),
        "avg_output_chars": sum(len(r["output"]) for r in records) // len(records),
    }


if __name__ == "__main__":
    import sys
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "chip_ai_agent/corpus/pcie_ovm"
    print(json.dumps(convert(src, dst), ensure_ascii=False, indent=2))
