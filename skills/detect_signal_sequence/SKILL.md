---
name: detect_signal_sequence
description: |
  Detect a value/state sequence, sequential transitions, or simultaneous events from a natural-language prompt, optionally within a time window and/or under a global gating condition.
target: [waveform]
examples:
  - "In CPU.fsdb, detect if tb_CPUsystem.i_CPUsystem.i_CPU.R_W rises then tb_CPUsystem.i_CPUsystem.i_CPU.BUSY rises within 100ns."
  - "In CPU.fsdb, when does tb_CPUsystem.i_CPUsystem.i_CPU.R_W go from 0 to 1 and then tb_CPUsystem.i_CPUsystem.i_CPU.BUSY go from 1 to 0 within 75ns."
  - "When do tb_CPUsystem.i_CPUsystem.i_CPU.CLOCK1, tb_CPUsystem.i_CPUsystem.i_pram.clock, and tb_CPUsystem.NewCard go high together? (in CPU.fsdb)"
  - "Did tb_CPUsystem.Card go through pattern 0100 -> 1011 -> 0111 in CPU.fsdb?"
  - "Find sequence of states IDLE -> LOAD -> DONE for signal fsm_sequence_tb.dut.curr_state in enum.fsdb."
  - "How many times is coffee_machine.i_operation_sel[2:0] equal to 4 and coffee_machine.state_nx[2:0] equal to IDLE?"
  - "How many times is <sigA> equal to <valueA> and <sigB> equal to <valueB> in <fsdb_file>?"
  - "Detect if the <nth> selected signal has value pattern <value1> -> <value2> -> <value3>."
  - "What is the start and end time of pattern 34->55->28 (radix in Hex) of signal system.i_cpu.data in rtl.fsdb?"
  - "In <fsdb_file>, detect if <sigA> rises then <sigB> rises within 100ns while (enable && mode==3)."
  - "Between 100ns and 500ns, find occurrences where <sigA> goes high and <sigB> goes low together; strictly after 100ns."
---

## Steps
- 1. Use `detect_signal_sequence()` when the prompt asks to detect value/state patterns (e.g., 0 -> 1 -> 2, IDLE -> LOAD -> DONE), ordered signal events (A then B within <time>), or simultaneous events (A and B go high together).
- 1.a. If the user asks separate counts for each signal (e.g., 'how many times A==4, and how many times B==IDLE'), do NOT use `detect_signal_sequence()`. Treat them as two sub-requests and use `find_signal_transition_to_value()` (with `count_only=True`) for each signal/value.
- 2. Set `user_prompt` to the user's original prompt. Do not rewrite 'selected signal(s)' references yourself; pass them as-is in `user_prompt`.
- 3. Decide the waveform file: if the prompt mentions current/active waveform (e.g., 'current waveform', 'active waveform', 'current FSDB'), omit `filename` (or set it to None) so the tool uses the active FSDB in nWave.
- 4. Decide the time window (optional):
- 4.a. If the prompt specifies a bounded window like 'between <start_time> and <end_time>', set `start_time=<start_time>` and `end_time=<end_time>`.
- 4.b. If the prompt specifies an open-ended start like 'after <time>' or 'from <time>', set `start_time=<time>`.
- 4.c. If the prompt implies exclusivity at the start boundary (e.g., 'strictly after <time>', 'next after <time>'), set `exclude_start_time=True`; otherwise keep default False.
- 4.d. Schema Correctness: do NOT output `exclude_start_time: null`. If exclusivity is not requested, either OMIT `exclude_start_time` or set it explicitly to `false`.
- 4.e. Do not set `end_time` (or `start_time`) for relative constraints like 'A then B within 100ns'. That 'within' constraint applies to the delay between transitions and should be encoded in the extracted transition list (e.g., `max_delay_from_prev`), not as an absolute time window.
- 4.f. 'after <time>' at the trailing position of a sequence sentence is the sequence-wide search start, even when it grammatically sits next to a transition verb. Set `start_time=<time>` for forms like:
-     - "... pattern X -> Y after <time>"
-     - "... goes through pattern X -> Y after <time>"
-     - "... takes value X and then later transitions to Y after <time>"
-     - "... transitions to Y after <time>" (when this is the only or final transition in a sequence sentence)
-     Do not encode that 'after <time>' as a per-transition delay (`max_delay_from_prev`, `min_delay_from_prev`, `exact_hold_duration`, etc.). 'after <time>' becomes a per-transition delay only when it clearly sits BETWEEN two adjacent transitions, e.g., "A goes high, after 20ns B goes low".
- 5. Decide `radix` (optional): if the prompt requests output format like 'show in hex/binary/decimal', set `radix` accordingly.
- 6. Decide `max_match_count`:
- 6.a. Set `max_match_count=0` ONLY when the prompt explicitly requests multiple results, such as:
-     - 'list timestamps', 'find the timestamps', 'at what times',
-     - 'list all', 'all occurrences', 'all times',
-     - 'how many times', 'count'.
- 6.b. If the prompt is phrased as 'When do/does ...?' without explicit multi-result wording, omit `max_match_count` (or set it to None) to report only the first match.
- 6.c. If the prompt asks for a single match explicitly (e.g., 'first', 'earliest', 'next occurrence'), omit `max_match_count` (or set it to None).
- 6.d. If the prompt asks for a specific number of matches (e.g., 'find 5 occurrences'), set `max_match_count=<N>`.
- 7. Global gating `condition` vs sequence target:
- 7.a. Treat conjunctions that DEFINE the target event/sequence (e.g., 'A==4 and B==IDLE' as a simultaneous target) as part of the SEQUENCE TARGET: keep them in `user_prompt` and do NOT set `condition`.
- 7.b. Set the explicit `condition=<sv_expr>` only when the user provides an ADDITIONAL gating constraint (separate from the target sequence) that must hold throughout the match, typically as a SystemVerilog boolean expression like '(enable && mode==3)'.
