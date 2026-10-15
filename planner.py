"""Pluggable planner layer: keyword baseline + OpenAI-compatible LLM planner.

Any OpenAI-compatible endpoint works: OpenAI, or local models (Ollama,
llama.cpp server, vLLM, LM Studio) via their /v1/chat/completions API.
The LLM planner always falls back to the keyword planner on any error, so the
agent never blocks on model availability.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

from .recipes import RECIPES, match_intent


class Planner(Protocol):
    def plan(self, intent: str) -> dict: ...
    def refine(self, intent: str, plan: dict, critique: str) -> dict: ...


class KeywordPlanner:
    """Baseline: trigger-word matching over curated recipes."""

    def plan(self, intent: str) -> dict:
        key = match_intent(intent)[0]
        return {"recipe": key, "steps": None, "reason": "keyword match"}


class LLMPlanner:
    """OpenAI-compatible chat-completions planner with strict-JSON output."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        temperature: float = 0.0,
        timeout: int = 30,
        registry_summary: str = "",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.temperature = temperature
        self.timeout = timeout
        self.registry_summary = registry_summary
        self.fallback = KeywordPlanner()

    # -- prompt -----------------------------------------------------------------
    def _system_prompt(self) -> str:
        recipes = json.dumps(
            {k: {"title": v["title"], "skills": [s["skill"] for s in v["steps"]]}
             for k, v in RECIPES.items()},
            ensure_ascii=False, indent=1,
        )
        return (
            "You are a chip design & verification debug planner.\n"
            "Available workflow recipes:\n" + recipes + "\n\n"
            "Available tool skills on this system:\n" + self.registry_summary + "\n\n"
            "Given the user intent, reply with ONLY a JSON object:\n"
            '{"recipe": "<recipe key>", "steps": ["<skill>", ...] | null, "reason": "<short>"}\n'
            "steps may be null to use the recipe's default order, or a reordered/"
            "reduced subset as you see fit. Only pick recipe keys and skills from "
            "the lists above."
        )

    # -- transport ---------------------------------------------------------------
    def _chat(self, intent: str) -> str:
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": intent},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]

    # -- validation ----------------------------------------------------------------
    @staticmethod
    def _validate(raw: str) -> dict:
        obj = json.loads(raw)
        recipe = obj.get("recipe")
        if recipe not in RECIPES:
            raise ValueError(f"unknown recipe: {recipe!r}")
        valid_skills = {s["skill"] for s in RECIPES[recipe]["steps"]}
        steps = obj.get("steps")
        if steps is not None:
            if not isinstance(steps, list) or not all(s in valid_skills for s in steps):
                raise ValueError("steps must be a list of skills from the recipe")
        return {"recipe": recipe, "steps": steps, "reason": str(obj.get("reason", ""))}

    def plan(self, intent: str) -> dict:
        try:
            return self._validate(self._chat(intent))
        except Exception as e:  # network/auth/model/JSON errors -> degrade
            fb = self.fallback.plan(intent)
            fb["reason"] = f"LLM planner unavailable ({e}); fell back: {fb['reason']}"
            return fb

    def refine(self, intent: str, plan: dict, critique: str) -> dict:
        """Plan-critique-retry: ask the model to revise its own plan.

        Falls back to the original plan if the revision is invalid.
        """
        prompt = (
            f"User intent: {intent}\n"
            f"Previous plan: {json.dumps(plan, ensure_ascii=False)}\n"
            f"Critique: {critique}\n"
            "Return the revised plan as ONLY the same JSON object format."
        )
        try:
            return self._validate(self._chat(prompt))
        except Exception:
            return plan


class ConversationalPlanner:
    """Multi-turn planner that feeds the previous RunReport summary back to the LLM.

    DVCon 2025-2026 agentic trend: verification agents must be stateful across
    turns — the last execution result (status, failing skills, counters) is the
    natural critique signal for the next planning round.
    """

    def __init__(self, inner: LLMPlanner):
        self.inner = inner
        self.last_report: dict | None = None

    def plan(self, intent: str) -> dict:
        plan = self.inner.plan(intent)
        if self.last_report:
            critique = self._critique_from_report()
            plan = self.inner.refine(intent, plan, critique)
        return plan

    def observe(self, report_summary: dict) -> None:
        """Record the last RunReport summary (from agent.run)."""
        self.last_report = report_summary

    def _critique_from_report(self) -> str:
        r = self.last_report or {}
        status = r.get("status", "unknown")
        failed = r.get("failed_skills") or []
        parts = [f"last run status: {status}"]
        if failed:
            parts.append(f"skills that failed: {', '.join(failed)}; avoid repeating them or reorder")
        else:
            parts.append("all steps succeeded; consider a follow-up/verification step")
        return "; ".join(parts)
