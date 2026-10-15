---
name: add_exclusions_for_uncovered_items
description: Exclude a single coverage item, bulk-exclude every uncovered coverage item/bin/failed assertion in a specific scope using the fast Tcl `-exclude` path, or exclude exactly the items listed in a user-supplied human-readable text file.
target: [coverage]
examples:
  # ---- Single-item exclusion (Mode A) ----
  - Exclude specific scope.
  - Exclude specific item.
  # ---- Bulk exclusion of uncovered items in a scope (Mode B) ----
  - Exclude all uncovered items of the whole design.
  - Exclude all uncovered items in specific scope.
  - Exclude all uncovered lines in specific scope.
  - Exclude uncovered toggle bins in specific scope.
  - Exclude uncovered FSM states/transitions in specific scope.
  - Exclude uncovered conditions in specific scope.
  - Exclude uncovered branches in specific scope.
  - Exclude failed assertions in specific scope.
  - Mark cross bins with hit count = 0 as excluded.
  - Exclude uncovered cover point bins in specific scope.
  - Exclude uncovered cross bins in specific scope.
  - Exclude uncovered bins in all cover groups.
  # ---- File-path exclusion from a human-readable text file (Mode C) ----
  - Exclude uncovered items listed in <file_path>.
  - Exclude covergroup bins listed in <file_path>.
  - Exclude assertions listed in <file_path>.
  - Exclude items in user_uncovered_items.txt.
  - Exclude covergroup bins in user_covergroup_bins.txt.
  - Exclude assertions in my_assertions.txt.
  - Exclude all uncovered cover point bins in <file_path>.
  - Exclude all uncovered cross bins in <file_path>.
  - Exclude all uncovered items in <file_path>.
  - Exclude failed assertions in <file_path>.
  - Apply the exclusions described in <file_path>.
---

# Add Exclusions for Uncovered Items

This skill supports three mutually exclusive modes. First classify the user's
request, then execute exactly one mode.

The bulk path (Mode B) relies on the Tcl command
`gen_cov_metric_info -scope <scope> -file <out> -out_format json -exclude`,
which excludes every uncovered Line / FSM / Toggle / Condition / Branch
item under `<scope>` at the covdb level in a **single** Tcl call. Failed
assertions still need the GUI path (see Mode B step 1.c) because the
Tcl command skips assertion metrics.

The file-path path (Mode C) honours **only** the items / bins /
assertions explicitly listed in a user-supplied text file. The
`add_exclusion(file_path=...)` tool accepts both the machine JSON
dumps produced by `list_uncovered_items` / `get_coverage_assertions`
/ `get_covergroup_bins` and the human-readable text format produced
by the bundled coverage codec; it auto-detects the shape and decodes
the text variants internally. Other uncovered items in the same
scope are left untouched.

## Mode classification

- **Mode A — Single-item exclusion.** The user names exactly one coverage item /
  bin / scope and asks to exclude it, with no language implying enumeration of
  uncovered items. Typical phrasings:
  - "Exclude `<item>`."
  - "Exclude scope `<scope>`."

- **Mode B — Bulk exclusion of uncovered items in a scope.** The user asks to
  exclude *all uncovered* (or *failed*, or *hit-count = 0*) items / lines /
  toggles / FSM states / conditions / branches / assertions / cover point bins
  / cross bins, optionally restricted to a `<scope>` or to all cover groups /
  the whole design. Typical phrasings include any of: "all uncovered", "all
  holes", "every uncovered", "failed assertions", "hit count = 0",
  "all cover groups", "whole design".

- **Mode C — File-path exclusion from a human-readable text file.** The user
  points at a text file on disk and asks to exclude the items / bins /
  assertions it lists. Typical phrasings include any of: "exclude the items
  in `<file_path>`", "exclude all uncovered <metric> bins in `<file_path>`",
  "apply the exclusions described in `<file_path>`", "use `<file_path>` to
  exclude", "exclude what's in this file", or the user drops a path that
  ends in `.txt` / `.log` containing a coverage payload. The file may
  already be in the standard text format produced by the coverage tools,
  **or** in a free-form human-readable variant (missing comment header,
  `scope:` instead of `@scope:`, missing `@type:` line, arbitrary
  indentation, etc.). The tool's codec auto-detects the standard text
  format; for non-standard variants the LLM SHOULD instead point the user
  at the standard-format file produced by `get_covergroup_bins` /
  `list_uncovered_items` / `get_coverage_assertions`, because the Coverage
  sub-agent has no shell / filesystem-write tools to normalise the file
  itself.

If the prompt is ambiguous:

- **File path wins.** If the prompt mentions a path token (anything
  containing `/`, ending in `.txt` / `.log`, or otherwise resolving to an
  on-disk file), pick **Mode C** -- *even when* the surrounding language
  matches a Mode B example such as "exclude all uncovered cover point bins
  in X". The `in <file_path>` clause shadows the `in <scope>` clause from
  Mode B because the path overrides any scope-name interpretation.
- Else, if it mentions a metric name (line / toggle / FSM / condition / branch
  / assertion / cover point / cross / covergroup / bin) or words like "all",
  "uncovered", "holes", "failed", "hit count = 0", prefer **Mode B**.
- Otherwise prefer **Mode A**.

## Steps

### Mode A — Single-item exclusion

1. Set `<item>` to the exact item / scope / bin name **as written in the user
   prompt**. Do not transform, expand, abbreviate, or substitute it.
   - `<item>` MUST come directly from the user's prompt.
   - `<item>` MUST NOT be derived, extracted, parsed, or otherwise read from
     the content of any file generated by Mode B / Mode C tools
     (`list_uncovered_items`, `get_coverage_assertions`,
     `get_covergroup_bins`), nor from any other file or tool result.
   - Do **not** call `list_uncovered_items`, `get_coverage_assertions`, or
     `get_covergroup_bins` in Mode A — not even to "look up" or "validate"
     `<item>`.
2. Call `add_exclusion(item=<item>)` directly. Do **not** pass `file_path`,
   `scope`, or `testbench` in this mode, and do **not** loop over multiple
   items.
3. Skip Mode B and Mode C; go to "Post-conditions".

### Mode B — Bulk exclusion of uncovered items in a scope

Always prefer the direct fast path (1.a / 1.b) over the legacy list-then-file
path (1.d). The fast path performs the exclusion in one Tcl round-trip per
scope; the legacy path is only kept as a fallback for assertion-only requests.

1. Execute exactly one of the following sub-steps:
   - 1.a. **Code-coverage holes** (Line / FSM / Toggle / Condition / Branch,
     or "all uncovered items in scope X", or "whole design"):
     - For a specific scope: call
       `add_exclusion(scope=<scope>, is_module=<bool>)`. The user's
       scope of choice is passed through unchanged. Set `is_module=True`
       only when the user explicitly refers to a module definition.
     - For "whole design" / "entire design" / "root scope" requests
       where the user does NOT name a scope: call
       `add_exclusion(is_root=True)`. The skill resolves the design
       root via `get_scope_name`, so you do not have to look up the
       top scope name yourself. Do not pair `is_root=True` with an
       explicit `scope` argument.
     - Do **not** call `list_uncovered_items` first; the Tcl `-exclude`
       option subsumes both list and exclusion in a single call.
   - 1.b. **Covergroup bins** (cover point / cross / "all cover groups" /
     "hit count = 0"):
     - For a specific covergroup scope (e.g. "Exclude uncovered bins
       in `<scope>`", "Exclude uncovered cover point bins in
       `<scope>`", "Exclude uncovered cross bins in `<scope>`"): call
       `add_exclusion(testbench=True, scope=<scope>)`. The user's
       scope is passed through unchanged and restricts the bin walk
       to that covergroup via
       `gen_cov_metric_info -scope <scope> -testbench -exclude`.
       `<scope>` MUST come directly from the user's prompt — do not
       transform, expand, abbreviate, or substitute it (covergroup
       scopes routinely contain `::`, e.g. `top.inst::cg`, and the
       full string must be preserved).
     - For design-wide requests where the user does NOT name a
       covergroup scope (e.g. "Exclude uncovered bins in all cover
       groups", "Mark cross bins with hit count = 0 as excluded"):
       call `add_exclusion(testbench=True)`. With no `scope` /
       `is_root`, the skill flips `-allcovergroup` so every
       uncovered covergroup bin in the design is excluded via
       `gen_cov_metric_info -testbench -allcovergroup -exclude`.
     - Do **not** call `get_covergroup_bins` first.
   - 1.c. **Failed assertions only** (the user explicitly asks for "failed
     assertions" and nothing else):
     - Use `get_coverage_assertions(<scope>, "Failure")` to obtain failed
       assertions in `<scope>`, capture the returned `<file_path>`.
     - Call `add_exclusion(file_path=<file_path>)`. The skill internally
       detects an assertion-only payload and falls back to the GUI
       assertion list view because the Tcl `-exclude` option skips
       assertion metrics on the C++ side.
   - 1.d. **Pre-filtered hole / bin lists** (rare — the user already has a
     payload produced by `list_uncovered_items` / `get_covergroup_bins` /
     `get_coverage_assertions` and wants exactly those leaves excluded):
     - Call `add_exclusion(file_path=<file_path>)`. The tool walks the
       payload tree and GUI-excludes **only the leaves explicitly listed**
       (per-metric subsetting *is* preserved, and sibling holes / bins
       under the same scope are left untouched). The fast Tcl
       `gen_cov_metric_info -exclude` path is *not* used for file
       payloads because it ignores file content and would over-exclude
       as soon as any subtree is curated / partial.
     - Mechanically this is the same code path as Mode C below; both
       routes converge on `_exclude_from_file`. Use Mode B 1.a / 1.b
       instead when you want bulk "exclude every uncovered item in
       scope X" semantics.

### Mode C — File-path exclusion from a human-readable text file

Use this mode when the user supplies a text file (`.txt` / `.log` / any
plain-text path) describing the exact items / bins / assertions they
want excluded. Mode C honours the file content exactly: only the leaf
items / bins / assertions actually listed are excluded — sibling holes in
the same scope are left alone. Use Mode B instead when the user wants
*every* uncovered item under a scope dropped.

The Coverage sub-agent has **no shell or filesystem-write tools** of
its own, so it cannot run the codec CLI or otherwise normalise the
file before handing it to `add_exclusion`. To keep the path open
anyway, `add_exclusion(file_path=...)` auto-detects JSON vs text and
decodes the text variants internally via the bundled
`_coverage_codec` (covergroup vs uncovered/assertions). Mode C
therefore collapses to a single tool call as long as the file is
already in the standard text format produced by
`get_covergroup_bins` / `list_uncovered_items` /
`get_coverage_assertions`; everything below — including the
fallback when the file is non-standard — follows from that single
constraint.

Inputs:

- `<input_txt>` — absolute path of the user-supplied text (or JSON)
  file containing the items / bins / assertions to exclude.

Steps:

1. **Sanity-check `<input_txt>` is in the standard format.** The
   coverage tools' standard formats are:

   - **`uncovered` and `assertions`** standard format:

     ```text
     # Format:
     #   <indent><key>                  -> inner node (children below)
     #   <indent><key><TAB><json-value> -> leaf with an explicit, JSON-
     #                                     encoded value.
     #

     <top_scope>
       <metric>            # e.g. Line / Toggle / FSM / Condition / Branch / Assert
         <item>
         <item>
         ...
     <next_top_scope>
       ...
     ```

     - Indentation is exactly two spaces per nesting level (no tabs).
     - A bare key with deeper-indented children is an inner node; a
       bare key with no deeper-indented line is an implicit-default
       leaf (`"Uncovered"`).

   - **`covergroup`** standard format:

     ```text
     # Format:
     #   @scope: <scope>
     #   @type:  <type>
     #   <bin_name>
     #

     @scope: <scope>
     @type:  <type>
     <bin_name>
     <bin_name>
     ...

     @scope: <next_scope>
     @type:  <next_type>
     ...
     ```

     - Every section MUST start with the two header lines
       `@scope: <scope>` and `@type:  <type>`.
     - A bare bin name is an implicit-default row (hit count = 0).
       Use `<hit_count><TAB><bin_name>` only when the source file
       carries an explicit non-zero hit count.
     - `<type>` is one of `cover point` or `cross`.

   - **Machine JSON** dumps produced by `list_uncovered_items` /
     `get_coverage_assertions` / `get_covergroup_bins` are also
     accepted as-is.

   If `<input_txt>` does **not** match any of the formats above
   (e.g. it lacks the `@scope:` header for covergroup bins, uses
   tabs instead of two-space indentation, or contains free-form
   prose), do **not** attempt to normalise it yourself (see the
   single-constraint note at the top of this mode). Instead, ask
   the user to regenerate the file through the corresponding tool
   (`get_covergroup_bins` / `list_uncovered_items` /
   `get_coverage_assertions`) and re-issue the prompt with the new
   path.

2. **Apply the exclusions** by calling
   `add_exclusion(file_path=<input_txt>)`. The tool auto-detects
   the payload format (JSON vs covergroup text vs uncovered/
   assertions text), decodes it via the bundled codec, and walks
   the resulting tree per leaf driving the appropriate GUI / Tcl
   exclusion path per artifact:
   - `uncovered` → per-scope, per-metric exclusion of the leaves
     listed (Line / Toggle / FSM / Condition / Branch + any
     assertions found under `Assert`).
   - `covergroup` → per-sample, per-bin exclusion of only the bins
     listed (sibling uncovered bins under the same sample are left
     untouched).
   - `assertions` → assertion list view exclusion of the leaves
     under each scope's `Assert` sub-bucket.

   Do **not** pair `file_path` with `scope`, `is_root`, `is_module`,
   `testbench`, or `item` in this mode.

## Post-conditions

3. Do not recalculate score after exclusion. The exclusion step intentionally
   leaves the displayed score unchanged so the user can compare before/after
   manually.
