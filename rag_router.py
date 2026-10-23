"""Unified RAG query router: routes a query to the right combination of indexes,
fuses results across all sources with normalized scoring, and returns a single
unified result.  This is the single entry point the agent should use instead of
calling individual index tools separately.

Supported backends:
  manual_ingest   - 133 technical manuals, 427k units (chapter/steps/flow/example/prose)
  uvm_methodology - 11 structured patterns, 35 pitfalls, phase maps, checklists
  uvm_semantic    - 2767 concept cards from UVM 1.2 source
  ug_index        - VCS + Verdi UG (35k chunks)
  dvcon_index     - DVCon 2025/2026 papers (method/conclusion)
  npi_index       - Synopsys NPI C API (22 families, 506 APIs)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagHit:
    """A single unified search hit from any backend."""
    source: str          # backend name
    kind: str            # unit kind (steps/flow/example/prose/section/chapter/concept/pattern)
    product: str
    doc: str
    title: str
    text: str
    score: float = 0.0   # normalized 0-1 (computed after fusion)
    raw_score: float = 0.0
    metadata: dict = field(default_factory=dict)


def _detect_intent(query: str) -> dict:
    """Detect what kind of RAG backends are most relevant for this query."""
    q = query.lower()
    return {
        "uvm_methodology": any(w in q for w in (
            "driver", "monitor", "agent", "scoreboard", "sequence", "env",
            "build_phase", "connect_phase", "run_phase", "factory override",
            "objection", "tlm", "register model", "phase", "handshake",
            "config_db", "uvm", "testbench", "checklist", "pitfall")),
        "manual_search": len(q.split()) >= 3,  # almost always relevant
        "uvm_semantic": any(w in q for w in (
            "uvm", "factory", "phase", "objection", "config", "sequence",
            "tlm", "port", "override", "register", "callback", "report")),
        "uvm_notes": any(w in q for w in (
            "uvm", "driver", "monitor", "agent", "scoreboard", "sequence",
            "sequencer", "factory", "override", "phase", "objection",
            "config_db", "register", "tlm", "callback", "report", "macro",
            "base", "component", "env", "test", "design pattern")),
        "ug_index": any(w in q for w in (
            "vcs", "verdi", "compile", "simulation", "coverage", "debug",
            "waveform", "fsdb", "sva", "assertion", "power", "upf")),
        "dvcon_index": any(w in q for w in (
            "methodology", "paper", "dvcon", "research", "trend", "ai",
            "machine learning", "coverage closure", "verification strategy")),
        "npi_index": any(w in q for w in (
            "npi", "fsdb", "c api", "waveform api", "coverage api")),
    }


def rag_search(query: str, top_k: int = 5, backends: list[str] | None = None,
               kind: str | None = None, product: str | None = None) -> dict:
    """Unified RAG search across all relevant indexes.

    Args:
        query: The search query.
        top_k: Maximum hits to return (after fusion and dedup).
        backends: Restrict to specific backends (default: auto-detect).
        kind: Filter by unit kind (steps/flow/example/prose/section/chapter/pattern).
        product: Filter by product (vcs/verdi/uvm/uvm_official).

    Returns:
        {"query": ..., "backends_used": [...], "total_hits": N, "hits": [...],
         "recommendations": [...]}  # next-tool recommendations
    """
    intent = _detect_intent(query)
    if backends is None:
        backends = [b for b, active in intent.items() if active]
        if not backends:
            backends = ["manual_search"]  # always fallback

    all_hits: list[RagHit] = []
    backend_status = {}

    # Parallel fan-out to all backends with per-backend timeout
    from .scheduler import cache_get, cache_put, dispatch_with_cache

    def _query_one(backend: str) -> tuple[str, list[RagHit], str | None]:
        try:
            # Check per-backend cache
            bargs = {"q": query, "k": top_k, "kind": kind, "product": product}
            cached = cache_get(f"rag_{backend}", bargs)
            if cached is not None:
                return backend, cached, None
            hits = _query_backend(backend, query, top_k=top_k, kind=kind, product=product)
            cache_put(f"rag_{backend}", bargs, hits)
            return backend, hits, None
        except Exception as e:
            return backend, [], str(e)

    rag_timeout = float(os.environ.get("CHIP_AGENT_RAG_TIMEOUT", "10"))
    if len(backends) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(len(backends), 6)) as pool:
            futures = {pool.submit(_query_one, b): b for b in backends}
            for future in as_completed(futures, timeout=rag_timeout):
                try:
                    bname, hits, err = future.result()
                    if err:
                        backend_status[bname] = {"ok": False, "error": err}
                    else:
                        backend_status[bname] = {"ok": True, "hits": len(hits)}
                        all_hits.extend(hits)
                except Exception as e:
                    bname = futures[future]
                    backend_status[bname] = {"ok": False, "error": str(e)}
    else:
        bname, hits, err = _query_one(backends[0])
        if err:
            backend_status[bname] = {"ok": False, "error": err}
        else:
            backend_status[bname] = {"ok": True, "hits": len(hits)}
            all_hits.extend(hits)

    # Normalize scores per backend (0-1 relative to top hit in that backend)
    by_backend: dict[str, list[RagHit]] = {}
    for h in all_hits:
        by_backend.setdefault(h.source, []).append(h)
    for backend, hits in by_backend.items():
        if not hits:
            continue
        max_score = max(h.raw_score for h in hits) or 1.0
        for h in hits:
            h.score = round(h.raw_score / max_score, 4)

    # Deduplicate by text prefix (first 200 chars, case-insensitive)
    seen: set[str] = set()
    deduped: list[RagHit] = []
    for h in sorted(all_hits, key=lambda x: -x.score):
        key = re.sub(r"\s+", " ", h.text[:200]).lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(h)

    # Sort by normalized score, take top_k
    deduped.sort(key=lambda x: -x.score)
    final_hits = deduped[:top_k]

    # Generate tool-chain recommendations based on what we found
    recommendations = _recommend_next_tools(final_hits, query)

    return {
        "query": query,
        "backends_used": backends,
        "backend_status": backend_status,
        "total_hits": len(final_hits),
        "hits": [
            {
                "source": h.source,
                "kind": h.kind,
                "product": h.product,
                "doc": h.doc,
                "title": h.title,
                "score": h.score,
                "text": h.text[:2000],
                "text_truncated": len(h.text) > 2000,
                **({"metadata": h.metadata} if h.metadata else {}),
            }
            for h in final_hits
        ],
        "recommendations": recommendations,
    }


def _query_backend(backend: str, query: str, top_k: int,
                   kind: str | None, product: str | None) -> list[RagHit]:
    """Query a single backend and return normalized RagHit objects."""
    if backend == "manual_search":
        from . import manual_ingest
        r = manual_ingest.search(query, kind=kind, product=product, top_k=top_k)
        return [
            RagHit(
                source="manual_search", kind=h.get("kind", "prose"),
                product=h.get("product", ""), doc=h.get("doc", ""),
                title=h.get("title", ""), text=h.get("text", ""),
                raw_score=h.get("score", 0),
                metadata={"chapter": h.get("chapter", ""),
                          "section": h.get("section", ""),
                          "source_path": h.get("source", "")},
            )
            for h in r.get("hits", [])
        ]

    if backend == "uvm_methodology":
        from . import uvm_methodology as um
        result = um.decide(query)
        hits = []
        if result.get("matched"):
            p = result.get("best_data", {})
            text_parts = []
            if p.get("decision"):
                text_parts.append(p["decision"])
            if p.get("handshake"):
                text_parts.append("Handshake: " + "; ".join(p["handshake"]))
            if p.get("pitfalls"):
                text_parts.append("Pitfalls: " + "; ".join(p["pitfalls"][:3]))
            hits.append(RagHit(
                source="uvm_methodology", kind="pattern",
                product="uvm", doc="uvm_methodology",
                title=f"Pattern: {result['best_pattern']}",
                text="\n".join(text_parts)[:2000],
                raw_score=1.0,  # methodology always scores top for matching intents
                metadata={"pattern": result["best_pattern"],
                          "rationale": result.get("best_rationale", ""),
                          "alternatives": result.get("alternatives", [])},
            ))
        return hits

    if backend == "uvm_semantic":
        from . import uvm_src_tools
        r = uvm_src_tools.semantic_search(query, top_k=top_k)
        # semantic_search returns a formatted string; parse if possible
        # For now, return as prose hits
        if isinstance(r, str) and r.strip():
            return [RagHit(
                source="uvm_semantic", kind="concept",
                product="uvm", doc="uvm_concept_cards",
                title=f"Concept: {query[:50]}",
                text=r[:2000], raw_score=0.8,
            )]
        return []

    if backend == "uvm_notes":
        from . import uvm_src_tools
        r = uvm_src_tools.search_notes(query, top_k=top_k)
        return [
            RagHit(
                source="uvm_notes", kind=h.get("kind", "prose"),
                product="uvm_notes", doc=h.get("subsystem", ""),
                title=h.get("title", ""), text=h.get("text", ""),
                raw_score=h.get("score", 0),
                metadata={"topic": h.get("topic", ""),
                          "source_file": h.get("source", "")},
            )
            for h in r.get("hits", [])
        ]

    if backend == "ug_index":
        from . import ug_index
        r = ug_index.search(query, product=product if product in ("vcs", "verdi") else None,
                           kind=kind if kind in ("chapter", "steps", "prose") else None,
                           top_k=top_k)
        return [
            RagHit(
                source="ug_index", kind=h.get("kind", "prose"),
                product=h.get("product", ""), doc=h.get("doc", ""),
                title=h.get("section", ""), text=h.get("section", ""),
                raw_score=h.get("score", 0),
                metadata={"chunk": h.get("chunk", 0)},
            )
            for h in r.get("hits", [])
        ]

    if backend == "dvcon_index":
        from . import dvcon_index
        r = dvcon_index.search(query, kind=kind if kind in ("method", "conclusion", "paragraph") else None,
                               top_k=top_k)
        return [
            RagHit(
                source="dvcon_index", kind=h.get("kind", "paragraph"),
                product="dvcon", doc=h.get("title", ""),
                title=h.get("title", ""), text=h.get("summary", h.get("text", "")),
                raw_score=h.get("score", 0),
                metadata={"year": h.get("year", ""), "venue": h.get("venue", "")},
            )
            for h in r.get("hits", [])
        ]

    if backend == "npi_index":
        from . import npi_index
        r = npi_index.search(query, top_k=top_k)
        return [
            RagHit(
                source="npi_index", kind="api",
                product="npi", doc=h.get("header", ""),
                title=h.get("name", ""), text=h.get("signature", ""),
                raw_score=1.0,  # NPI uses exact match, not score
            )
            for h in r.get("results", [])
        ]

    return []


# ---------------------------------------------------------------------------
# Tool-chain recommendation engine
# ---------------------------------------------------------------------------

_WORKFLOW_CHAINS = {
    "driver": ["chip_uvm_methodology(op=pattern,pattern=driver)",
               "chip_uvm_method_source(class=uvm_driver)",
               "chip_generate_testbench",
               "chip_check_uvm_compliance",
               "chip_run_simulation"],
    "monitor": ["chip_uvm_methodology(op=pattern,pattern=monitor)",
                "chip_uvm_method_source(class=uvm_monitor)",
                "chip_generate_testbench",
                "chip_check_uvm_compliance"],
    "agent": ["chip_uvm_methodology(op=pattern,pattern=agent)",
              "chip_generate_testbench",
              "chip_check_uvm_compliance"],
    "scoreboard": ["chip_uvm_methodology(op=pattern,pattern=scoreboard)",
                   "chip_uvm_method_source(class=uvm_scoreboard)",
                   "chip_generate_testbench",
                   "chip_check_uvm_compliance"],
    "sequence": ["chip_uvm_methodology(op=pattern,pattern=sequence)",
                 "chip_uvm_method_source(class=uvm_sequence)",
                 "chip_generate_testbench"],
    "env": ["chip_uvm_methodology(op=pattern,pattern=env)",
            "chip_generate_testbench",
            "chip_check_uvm_compliance",
            "chip_run_simulation"],
    "register_model": ["chip_uvm_methodology(op=pattern,pattern=register_model)",
                       "chip_uvm_method_source(class=uvm_reg_block)",
                       "chip_generate_testbench"],
    "compile_error": ["chip_analyze_eda_log",
                      "chip_manual_search(kind=steps)",
                      "chip_run_simulation"],
    "coverage_gap": ["chip_dvcon_search(failure_class=coverage_gap)",
                     "chip_manual_search(kind=steps)",
                     "chip_coverage_driven_stimulus"],
    "assertion_fail": ["chip_dvcon_search(failure_class=assertion)",
                       "chip_manual_search(kind=example)"],
    "simulation_hang": ["chip_uvm_methodology(op=pattern,pattern=objection_lifecycle)",
                        "chip_manual_search(query=objection drain_time)"],
}


def _recommend_next_tools(hits: list[RagHit], query: str) -> list[dict]:
    """Based on search results and query intent, recommend the next tool chain."""
    recs = []
    q = query.lower()

    # If we found a methodology pattern, recommend the full workflow chain
    for h in hits:
        if h.source == "uvm_methodology" and h.kind == "pattern":
            pattern = h.metadata.get("pattern", "")
            chain = _WORKFLOW_CHAINS.get(pattern, [])
            if chain:
                recs.append({
                    "trigger": f"methodology pattern: {pattern}",
                    "chain": chain,
                    "reason": f"Complete workflow for building {pattern} component",
                })
            break

    # If the query mentions specific failure types
    if any(w in q for w in ("compile error", "build fail", "syntax error")):
        recs.append({"trigger": "compile error", "chain": _WORKFLOW_CHAINS["compile_error"],
                     "reason": "Error diagnosis workflow"})
    if any(w in q for w in ("coverage gap", "coverage not closed", "covergroup")):
        recs.append({"trigger": "coverage gap", "chain": _WORKFLOW_CHAINS["coverage_gap"],
                     "reason": "Coverage closure workflow"})
    if any(w in q for w in ("assertion fail", "sva fail", "property fail")):
        recs.append({"trigger": "assertion failure", "chain": _WORKFLOW_CHAINS["assertion_fail"],
                     "reason": "Assertion debug workflow"})
    if any(w in q for w in ("hang", "objection", "phase stuck", "timeout")):
        recs.append({"trigger": "simulation hang", "chain": _WORKFLOW_CHAINS["simulation_hang"],
                     "reason": "Hang/objection debug workflow"})

    return recs


def status() -> dict:
    """Report which backends are available and their health."""
    backends = ["manual_search", "uvm_methodology", "uvm_semantic",
                "uvm_notes", "ug_index", "dvcon_index", "npi_index"]
    health = {}
    for b in backends:
        try:
            hits = _query_backend(b, "test", top_k=1, kind=None, product=None)
            health[b] = {"ok": True, "test_hits": len(hits)}
        except Exception as e:
            health[b] = {"ok": False, "error": str(e)}
    return {"backends": health, "workflow_chains": list(_WORKFLOW_CHAINS.keys())}
