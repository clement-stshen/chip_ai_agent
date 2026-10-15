---
name: get_power_objects
description: |
  Simple skill to list UPF power objects under a scope
target: [power]
examples:
  - "Get all power domains in the design."
  - "Get power domains under scope system."
  - "Get supply sets under scope system include sub-scope."
---

## Steps
- 0. If not providing the scope, please call get_power_top() to get the top scope first.
- 1. Call `get_power_objects()` with:
  - `scope`: user scope or design top scope.
  - `object_type`: one of `powerdomain`, `supplyset`, `supplysethandle`, `supplynet`, `supplyport`, `powerswitch`, `isolation`, `retention`, `pst`.
  - `transitive`:
    - `True` when user says "all ... in the design" or explicitly asks to include sub-scopes.
    - `False` when user says "under scope X" without sub-scope wording.
  - `limit`:
    - use user value if provided.
    - otherwise use default `1000`.
- 2. Return concise counts and representative names from the result.
- 3. If result is large, suggest narrowing `scope` or reducing `limit`.
