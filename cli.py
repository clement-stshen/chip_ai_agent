"""CLI: python -m chip_ai_agent.cli "why is this signal X" [--skills DIR] [--server CMD...]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent import ChipAgent
from .planner import LLMPlanner


def main():
    p = argparse.ArgumentParser(prog="chip-agent")
    p.add_argument("intent", nargs="?", default="",
                   help="natural-language task, e.g. 'trace X at u_core/dout'")
    p.add_argument("--skills",
                   default=str(Path(__file__).parent / "skills"),
                   help="skills directory (default: agent's own dir with all "
                        "123 Synopsys skills + built-in methodology skills)")
    p.add_argument("--extra-skills", action="append", default=None,
                   help="additional skills directory (repeatable); default adds "
                        "the vendored digital-chip-design-agents plugins tree")
    p.add_argument("--experience", default=None,
                   help="experiences.jsonl path: auto-record failures and inject past fixes into planning")
    p.add_argument("--server", nargs=argparse.REMAINDER, help="MCP server command")
    p.add_argument("--db", default=None, help="SQLite path to persist RunReports")
    p.add_argument("--history", action="store_true", help="show recent runs and exit")
    p.add_argument("--stats", action="store_true", help="skill success-rate stats and exit")
    p.add_argument("--planner", choices=["keyword", "llm"], default="keyword")
    p.add_argument("--model", default="gpt-4o-mini", help="LLM planner model name")
    p.add_argument("--base-url", default="https://api.openai.com/v1",
                   help="OpenAI-compatible endpoint (e.g. Ollama: http://localhost:11434/v1)")
    args = p.parse_args()

    default_extra = [str(Path(__file__).resolve().parent / "digital" / "plugins")]
    agent = ChipAgent(args.skills, mcp_command=args.server or None, db_path=args.db,
                      extra_skills_dirs=args.extra_skills or default_extra,
                      experience_path=args.experience)
    if args.planner == "llm":
        agent.planner = LLMPlanner(
            model=args.model, base_url=args.base_url,
            registry_summary=agent.registry.summary(),
        )

    if args.history:
        if not agent.store:
            print("error: --history requires --db", file=sys.stderr)
            return 2
        for r in agent.store.history():
            print(r)
        return 0
    if args.stats:
        if not agent.store:
            print("error: --stats requires --db", file=sys.stderr)
            return 2
        for skill, total, ok in agent.store.skill_success_rate():
            print(f"{skill:60s} {ok}/{total}")
        return 0

    print(agent.registry.summary())
    report = agent.run(args.intent)
    print("\n" + report.render())
    if args.planner == "llm":
        print(f"\nPlanner: {agent.planner.__class__.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
