#!/usr/bin/env bash
# Bundle a fully offline deployment package: code + wheelhouse + site data.
# On the target machine: extract, set CHIP_AGENT_* env vars, run
#   bash chip_ai_agent/install_offline.sh && bash chip_ai_agent/install_integration.sh
set -euo pipefail

OUT="${1:-${CHIP_AGENT_BUNDLE_OUT:-$PWD/chip_ai_agent_offline_bundle.tar.gz}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/chip_ai_agent"
# ① 代码与随包数据
cp -r "$ROOT/chip_ai_agent" "$TMP/"
# ② 依赖 wheels (随包位于 chip_ai_agent/wheelhouse)
cp -r "$ROOT/chip_ai_agent/wheelhouse" "$TMP/"
# ③ 核心模板工程
cp -r "$ROOT/uvm_tb" "$TMP/"
# ④ 站点数据 (可选, 缺失时对应工具优雅降级)。
# 路径全部来自 CHIP_AGENT_* 环境变量, 脚本不携带任何站点特定绝对路径。
PY_CODE='
from pathlib import Path
import os
import importlib.util
spec = importlib.util.spec_from_file_location(
    "site_paths", str(Path(os.environ["AGENT"]) / "site_paths.py"))
sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
for p in (sp.UG_ROOT, sp.UVM_ROOT, sp.NPI_ROOT, sp.UART_EXAMPLE):
    print(p)
'
mapfile -t SITE_PATHS < <(AGENT="$AGENT" python3 -c "$PY_CODE" 2>/dev/null || true)
for src in "${SITE_PATHS[@]}"; do
  [ -n "$src" ] && [ -e "$src" ] && cp -r "$src" "$TMP/site_data/$(basename "$src")" || true
done

tar -czf "$OUT" -C "$TMP" chip_ai_agent wheelhouse uvm_tb site_data 2>/dev/null || \
tar -czf "$OUT" -C "$TMP" chip_ai_agent wheelhouse uvm_tb
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1))"
echo "部署: 解包后 set CHIP_AGENT_NPI_ROOT/CHIP_AGENT_UVM_ROOT/CHIP_AGENT_UG_ROOT"
echo "      /CHIP_AGENT_EXAMPLE_UART 指向 site_data/<name>, 再跑 install_offline.sh"
