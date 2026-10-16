"""Capability registry: scan skills directories, parse front matter,
classify skills by domain and routing target.

Supports the Synopsys SKILL.md format (multi-line YAML front
matter with `description: |` blocks, `target: [...]` routing metadata,
`examples:` lists) as well as the simple `# Title` markdown format used
by the built-in methodology skills. Duplicate skill names (e.g. a skill
present both flat and nested under a grouping dir) resolve first-wins
with the duplicates reported, so scans are deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    name: str
    path: Path | None
    domains: set[str] = field(default_factory=set)
    unparseable: bool = False
    target: str | None = None
    description: str = ""


DOMAIN_RULES: list[tuple[str, str]] = [
    ("debug_trace", r"^trace_|_workflow$|static_connectivity|search_and_trace"),
    ("debug_trace", r"^trace_signal$|^jump_to_source$|^detect_unknown"),
    ("waveform", r"waveform|fsdb|signal_value|signal_transition|signal_event|first_value|last_value|max_latency|signal_duration|detect_signal_sequence|nth_transition|switching|add_signals|set_radix|add_counter|active_temporal"),
    ("assertion", r"assertion|handshake"),
    ("coverage", r"uncovered|coverage"),
    ("power", r"power"),
    ("design_exploration", r"hierarchy|module|port|instance|interface|top_module|design_object|micro_architecture|explain_design|import_design|reload|check_if_design|get_info|exploration|scopes"),
    ("source_search", r"grep|search|source_code|read_specific|code_pattern|always_blocks|case_statements|force_statements|tasks_and_functions|parameters"),
    ("verification_flow", r"verification|orchestration|signoff|memory-keeper"),
    ("verification_flow", r"uvm|testbench"),
    ("formal_flow", r"^formal"),
    ("rtl_design", r"rtl"),
    ("pipeline_orchestration", r"pipeline|memory-keeper"),
]

# Synopsys skill packages route queries to sub-agents via `target`.
# When keyword rules fail, the declared target is the authoritative domain.
TARGET_DOMAINS: dict[str, str] = {
    "design": "design_exploration",
    "design_exploration": "design_exploration",
    "protocol": "design_exploration",
    "waveform": "waveform",
    "power": "power",
    "assertion": "assertion",
    "coverage": "coverage",
    "statictrace": "debug_trace",
    "activetrace": "debug_trace",
    "verdimaster": "debug_trace",
    "onesearch": "source_search",
}


def _classify(name: str, target: str | None) -> set[str]:
    out = {d for d, pat in DOMAIN_RULES if re.search(pat, name)}
    if not out and target and target in TARGET_DOMAINS:
        out.add(TARGET_DOMAINS[target])
    return out


def parse_front_matter(text: str) -> dict:
    """Parse a SKILL.md YAML front matter into a flat dict.

    Handles `key: value`, `description: |` multi-line blocks, `key:` followed
    by nested indented maps, and `-` list items (captured under their key).
    Returns {} when there is no front matter.
    """
    out: dict[str, str] = {}
    if not text.startswith("---"):
        return out
    rest = text[3:]
    if "---" not in rest:
        return out
    end = rest.index("---")
    lines = rest[:end].strip().splitlines()
    cur: str | None = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if not raw[0].isspace() and ":" in stripped:
            k, v = stripped.split(":", 1)
            cur = k.strip()
            out[cur] = v.strip()
        elif cur is not None:
            # continuation: `description: |` body or list/nested content
            out[cur] = (out[cur] + "\n" + raw.rstrip()).strip("\n")
    return out


class SkillRegistry:
    def __init__(self, skills_dir: str | Path, extra_dirs: list[str | Path] | None = None):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, Skill] = {}
        self.duplicates: list[tuple[str, Path, Path]] = []
        self._seen_paths: set[Path] = set()
        self._scan(self.skills_dir)
        for d in extra_dirs or []:
            self._scan(Path(d))

    def _scan(self, root: Path) -> None:
        if not root.exists():
            return
        # rglob supports both flat (dir/SKILL.md) and nested layouts
        # (group/skill/SKILL.md, plugins/<domain>/skills/<skill>/SKILL.md).
        for md in sorted(root.rglob("SKILL.md")):
            resolved = md.resolve()
            if resolved in self._seen_paths:      # same file scanned via two roots
                continue
            self._seen_paths.add(resolved)
            name = md.parent.name
            text = md.read_text(errors="ignore")
            if name in self.skills:
                # deterministic first-wins: sorted rglob order = shallowest
                # path wins, so a flat skill beats a nested duplicate
                self.duplicates.append((name, self.skills[name].path, md))
                continue
            fm = parse_front_matter(text)
            raw_target = fm.get("target", "").strip()
            # "[design]" / "[a, b]" / "a" — store the first canonical target;
            # raw multi-target strings previously never matched TARGET_DOMAINS
            target = None
            if raw_target:
                inner = raw_target.strip("[] ").strip()
                first = inner.split(",")[0].strip() if inner else ""
                target = first or None
            self.skills[name] = Skill(
                name=name,  # canonical key: always the directory name (recipes look up by it)
                path=md,
                domains=_classify(name, target),
                unparseable=text[:64].startswith("gAAAA"),
                target=target,
                description=" ".join(fm.get("description", "").split())[:200],
            )

    def by_domain(self, domain: str) -> list[str]:
        return [s.name for s in self.skills.values() if domain in s.domains]

    def domains(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for s in self.skills.values():
            for d in s.domains:
                out.setdefault(d, []).append(s.name)
        return out

    def by_target(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for s in self.skills.values():
            if s.target:
                out.setdefault(s.target, []).append(s.name)
        return out

    def summary(self) -> str:
        n = len(self.skills)
        enc = sum(s.unparseable for s in self.skills.values())
        lines = [f"skills={n} unparseable={enc}"]
        for d, names in sorted(self.domains().items()):
            lines.append(f"  {d}: {len(names)}")
        tgt = self.by_target()
        if tgt:
            lines.append("targets: " + " ".join(f"{t}:{len(v)}" for t, v in sorted(tgt.items())))
        if self.duplicates:
            lines.append(f"duplicates(dropped): {len(self.duplicates)}")
        return "\n".join(lines)

    @staticmethod
    def parse_skill_md(text: str) -> dict:
        """Parse a SKILL.md into name/description/sections.

        Returns {"unparseable": True} for opaque (unparseable) skill content;
        handles the common front-matter + markdown structure, including
        multi-line YAML values, `target` routing metadata and `examples` lists.
        """
        if text[:64].startswith("gAAAA"):
            return {"unparseable": True}
        out: dict = {}
        fm = parse_front_matter(text)
        out.update(fm)
        body = text
        if text.startswith("---") and "---" in text[3:]:
            end = text.index("---", 3)
            body = text[end + 3:]
        if fm.get("name"):
            out["name"] = fm["name"]
        elif body.lstrip().startswith("#"):
            out["name"] = body.lstrip().splitlines()[0].lstrip("# ").strip()
        # targets arrive as "[design]" / "[a, b]" raw strings
        for key in ("target",):
            raw = out.get(key, "")
            if raw.startswith("["):
                items = [x.strip() for x in raw.strip("[] ").split(",") if x.strip()]
                out[key] = items if len(items) != 1 else items[0]
        sections: dict[str, list[str]] = {}
        cur: str | None = None
        for ln in body.splitlines():
            if ln.startswith("#"):
                cur = ln.lstrip("# ").strip().lower()
                sections[cur] = []
            elif cur is not None:
                sections[cur].append(ln)
        out["sections"] = {k: "\n".join(v).strip() for k, v in sections.items()}
        return out
