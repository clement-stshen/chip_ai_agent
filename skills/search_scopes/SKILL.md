---
name: search_scopes
description: |
  Search and filter scopes in FSDB files based on various criteria including scope location, scope name patterns, scope type, and module names.
target: [waveform]
examples:
  - "Check existence of the scope <scope_name>"
  - "List all scopes with <name_pattern> under <target_scope>"
  - "List power domain under <target_scope>"
---

## Steps
- 1. First, call `search_scope()` with best-effort args from the user prompt (e.g. `target_scope`, `scope_name_pattern`/`module_name_pattern`, `scope_type`, `recursive`).
- 2. If `search_scope()` returns NIY / not implemented:
- 2.a. Explain the limitation explicitly: scope search is not supported yet, so the agent cannot reliably list scopes or prove a scope exists/non-exists via tools.
- 2.b. Do NOT try to substitute with `search_signal()` to 'prove' scope existence; that can cause false negatives (scope may contain no matching signals, or only sub-scopes).
- 2.c. For scope-type questions (e.g. 'power domain'), do NOT claim other tools can answer it. The reliable next step is user-driven: check the hierarchy/power view in Verdi and share the scope path(s).
- 2.d. `get_active_scope()` is ONLY helpful to capture the exact currently selected scope path string (to avoid typos). It does NOT indicate scope type (e.g. power domain).
- 2.e. For generic scope-name pattern exploration, ask the user to provide the exact full hierarchical scope path as shown in Verdi (copy/paste), optionally obtained by selecting it and running `get_active_scope()`.
