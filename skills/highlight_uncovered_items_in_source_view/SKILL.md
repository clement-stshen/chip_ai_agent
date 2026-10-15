---
name: highlight_uncovered_items_in_source_view
description: Highlight a single coverage item in the Source View, or highlight the first coverage item described in a human-readable text file produced by the coverage tools.
target: [coverage]
examples:
  # ---- Single coverage item (Mode A) ----
  - Highlight line <line_no> in <scope>.
  - Highlight toggle <bus[bit]> in <scope>.
  - Highlight FSM state <state_var> in <scope>.
  - Highlight FSM transitions of <state_var> in <scope>.
  - Highlight condition <expr> in <scope>.
  - Highlight branch <label> in <scope>.
  - Highlight assertion <path> in <scope>.
  - Highlight covergroup bin <bin> in <scope>::Cvr.<point>.
  # ---- First coverage item from a human-readable text file (Mode B) ----
  - Highlight uncovered lines in specific scope.
  - Show uncovered toggle bins highlights in specific scope.
  - Visualize FSM transitions in source view in specific scope.  
  - Show uncovered condition highlights in specific scope.
  - Can you show branch coverage annotations in specific scope?
  - Highlight coverage items listed in <file_path>.
  - Highlight covergroup bins listed in <file_path>.
  - Highlight assertions listed in <file_path>.
---

# Highlight Uncovered Items in Source View

This skill supports two mutually exclusive modes. First classify the user's
request, then execute exactly one mode.

`highlight_source_code` is a pure GUI side-effect: it drills the Coverage
GUI into one specific coverage item / bin in the Source View. It does
**not** mutate covdb state, recompute scores, or change the report
layout, so it is always safe to call repeatedly while iterating on a
prompt.

## Mode classification

- **Mode A — Single coverage item.** The user names exactly one coverage
  item / bin / scope and asks to highlight it in the Source View, with
  no language implying enumeration of uncovered items. Typical
  phrasings:
  - "Highlight `<item>` in scope `<scope>`."
  - "Show line `<line_no>` of `<scope>` in source."
  - "Drill into bin `<bin>` of `<scope>::Cvr.<point>`."

- **Mode B — First coverage item from a human-readable text file.**
  The user points at a payload that already exists on disk -- typically
  a previous result of `list_uncovered_items` /
  `get_coverage_assertions` / `get_covergroup_bins` -- and asks to
  highlight what it lists, OR the user phrases the request in
  enumerative terms ("show uncovered toggles in scope X") that already
  flow through the existing list-then-highlight pipeline.

If the prompt is ambiguous:

- **File path wins.** If the prompt mentions a path token (anything
  containing `/`, ending in `.txt` / `.log` / `.json`, or otherwise
  resolving to an on-disk file), pick **Mode B** -- *even when* the
  surrounding language matches a Mode A example.
- Else, if the prompt enumerates uncovered items in a scope (words
  like "all", "uncovered", "holes", "every"), prefer **Mode B** by
  generating the file via `list_uncovered_items` /
  `get_coverage_assertions` / `get_covergroup_bins` first.
- Otherwise prefer **Mode A**.

## Steps

### Mode A — Single coverage item

1. Set `<scope>`, `<metric>`, and `<item>` to the exact values **as
   written in the user prompt**. Do not transform, expand, abbreviate,
   or substitute them.
   - `<scope>`, `<metric>`, and `<item>` MUST come directly from the
     user's prompt.
   - `<metric>` is one of `Line` / `Toggle` / `FSM` / `Condition` /
     `Branch` / `Assert` (code coverage) or `covergroup` (functional
     coverage).
   - For `metric='covergroup'`, `<scope>` is the covergroup sample
     scope, which already carries the `::Cvr.<point>` suffix (e.g.
     `test_jukebox.st0.coin1::Cvr.RD`); `<item>` is the bin name (e.g.
     `HIGH`, `WAYHIGH_23`, `[HIGH],[MED]` for a cross bin).
   - For `metric='FSM'` you MAY additionally pass
     `fsm_type=states|transitions|sequences` to land the selection on
     the matching list-mode tab. Skip `fsm_type` if the user did not
     name one.
   - For module-definition scopes set `is_module=True`. Default
     (instance scope) otherwise.
2. Call
   `highlight_source_code(scope=<scope>, metric=<metric>, item=<item>, is_module=<bool>, fsm_type=<fsm_type>)`
   directly. Do **not** pass `file_path` in this mode, and do **not**
   loop over multiple items.
3. Skip Mode B; go to "Post-conditions".

### Mode B — First coverage item from a human-readable text file

Use this mode when the user supplies a coverage payload file (or asks
for an enumerative result that flows through one). Mode B highlights
**only the first** item in the file -- the
`add_exclusions_for_uncovered_items` skill is the place to look if the
user wants every listed item acted on.

The Coverage sub-agent has **no shell or filesystem-write tools** of
its own, so it cannot run the codec CLI or otherwise normalise the
file before handing it to `highlight_source_code`. To keep the path
open anyway, `highlight_source_code(file_path=...)` auto-detects JSON
vs text and decodes the text variants internally via the bundled
`_coverage_codec` (covergroup vs uncovered/assertions). Mode B
therefore collapses to one or two tool calls as long as the file is
already in the standard text format produced by
`list_uncovered_items` / `get_coverage_assertions` /
`get_covergroup_bins`; everything below -- including the fallback
when the file is non-standard -- follows from that single constraint.

Inputs:

- `<file_path>` — absolute path of the coverage payload file. Either a
  user-supplied path, or the path returned by a fresh
  `list_uncovered_items(...)` / `get_coverage_assertions(...)` /
  `get_covergroup_bins(...)` call when the user asked for an
  enumerative result.

Steps:

1. Obtain `<file_path>`.
   - If the user supplied a path token, use it directly.
   - Otherwise, generate the file from the matching tool:
     - "uncovered code-coverage holes" → `list_uncovered_items(...)`
       (produces `uncovered_items.txt`).
     - "failed assertions" → `get_coverage_assertions(...)` (produces
       `assertions.txt`).
     - "covergroup bins" → `get_covergroup_bins(...)` (produces
       `covergroup_bins.txt`).
2. **Sanity-check `<file_path>` is in the standard format.** The
   coverage tools' standard text formats are:

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
     - `<scope>` carries the `::Cvr.<point>` suffix (e.g.
       `test_jukebox.st0.coin1::Cvr.RD`).
     - A bare bin name is an implicit-default row (hit count = 0).
       Use `<hit_count><TAB><bin_name>` only when the source file
       carries an explicit non-zero hit count.
     - `<type>` is one of `cover point` or `cross`.

   - **Machine JSON** dumps produced by `list_uncovered_items` /
     `get_coverage_assertions` / `get_covergroup_bins` are also
     accepted as-is.

   If `<file_path>` does **not** match any of the formats above,
   do **not** attempt to normalise it yourself. Instead, ask the
   user to regenerate the file through the corresponding tool
   (`list_uncovered_items` / `get_coverage_assertions` /
   `get_covergroup_bins`) and re-issue the prompt with the new
   path.
3. **Highlight the first item** by calling
   `highlight_source_code(file_path=<file_path>)`. The tool
   auto-detects the payload format (JSON vs covergroup text vs
   uncovered/assertions text), decodes it via the bundled codec,
   and drives the appropriate per-shape GUI navigation:
   - `uncovered` / `assertions` → drill into the design / module
     hierarchy, open the matching detail tab (Line / Toggle / FSM /
     Condition / Branch / Assert), and select the first item under
     the first scope.
   - `covergroup` → activate the Function Groups tab, drill into
     the first sample scope (which carries the `::Cvr.<point>`
     suffix), and select the first bin in the covergroup detail
     view.

   Do **not** pair `file_path` with `scope`, `metric`, `item`,
   `is_module`, or `fsm_type` in this mode -- the file-path branch
   shadows the Mode A fields.

## Post-conditions

4. Do not recalculate score after highlighting. The highlight step
   is a pure GUI side-effect and intentionally leaves the displayed
   score and the covdb state unchanged so the user can compare
   before/after manually.
