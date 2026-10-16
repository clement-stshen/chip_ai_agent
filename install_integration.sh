#!/usr/bin/env bash
# One-shot integration of chip-ai-agent into Claude Code + Codex (+ VS Code extensions).
# Idempotent: safe to re-run. Zero dependencies (stdlib-only MCP server).
#
# Usage:
#   bash install_integration.sh          # methodology skills only (13)
#   bash install_integration.sh --all    # + all site skills
set -euo pipefail

AGENT="${CHIP_AGENT_HOME:-$(cd "$(dirname "$0")" && pwd)}"
# Python runtime: prefer an explicit override, then a sibling .venv (carries
# numpy + MCP SDK for full corpus support), then system python3.
if [ -n "${CHIP_AGENT_PYTHON:-}" ]; then
    PY="$CHIP_AGENT_PYTHON"
elif [ -x "$AGENT/../.venv/bin/python" ]; then
    PY="$AGENT/../.venv/bin/python"
else
    PY="python3"
fi
SKILLS_SRC=$AGENT/skills
INSTALL_ALL=0
[ "${1:-}" = "--all" ] && INSTALL_ALL=1

# built-in methodology skills (always installed)
METHODOLOGY="agentic_debug_workflow analyze_eda_log assertion_feedback_refine \
check_eda_tools check_uvm_compliance coverage_driven_stimulus generate_testbench \
formal_failure_debug open_waveform run_simulation sva_assertion_generation uvm_methodology \
vplan_coverage_traceability waveform_causal_diagnosis"

echo "== 1. Claude Code: register MCP server (user scope) =="
if claude mcp list 2>/dev/null | grep -q "chip-agent"; then
    echo "   already registered"
else
    claude mcp add chip-agent -s user -- "$PY" "$AGENT/mcp_server.py"
fi

echo "== 2. Codex: register MCP server (~/.codex/config.toml) =="
AGENT="$AGENT" PY="$PY" python3 - <<'PY'
import os, re
from pathlib import Path
cfg = Path.home()/".codex/config.toml"
s = cfg.read_text() if cfg.exists() else ""
block = '[mcp_servers.chip_agent]\ncommand = "%s"\nargs = ["%s"]\n' % (
    os.environ["PY"], os.environ["AGENT"] + "/mcp_server.py")
pat = re.compile(r'\[mcp_servers\.chip_agent\]\n(?:.+\n)*?(?=\[|\Z)')
if "mcp_servers.chip_agent" in s:
    if s[pat.search(s).start():pat.search(s).end()] == block:
        print("   already present")
    else:
        cfg.write_text(pat.sub(block, s, count=1))
        print("   updated (python/args refreshed)")
else:
    cfg.write_text(s.rstrip() + "\n\n" + block)
    print("   added")
PY

echo "== 3. Install skills to Claude Code + Codex skill dirs =="
for d in ~/.claude/skills ~/.codex/skills; do
    mkdir -p "$d"
    for name in $METHODOLOGY; do
        if [ -d "$SKILLS_SRC/$name" ]; then
            mkdir -p "$d/$name"
            cp -r "$SKILLS_SRC/$name/." "$d/$name/"
        fi
    done
    if [ "$INSTALL_ALL" = 1 ]; then
        # every flat skill plus the design_exploration group (33 nested skills)
        for s in "$SKILLS_SRC"/*/; do
            name=$(basename "$s")
            case " $METHODOLOGY " in *" $name "*) continue ;; esac
            [ "$name" = "design_exploration" ] && continue
            mkdir -p "$d/$name"
            cp -r "$s/." "$d/$name/"
        done
        mkdir -p "$d/design_exploration"
        cp -r "$SKILLS_SRC/design_exploration/." "$d/design_exploration/"
    fi
    echo "   $d: $(ls "$d" | wc -l) top-level skill dirs"
done

echo "== 4. Health check =="
claude mcp list 2>/dev/null | grep chip-agent || true
codex mcp list 2>/dev/null | grep chip_agent || true
echo "Done. In Claude/Codex say: '用 chip-agent 生成 testbench'"
