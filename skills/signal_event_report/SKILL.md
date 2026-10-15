---
name: signal_event_report
description: |
  Generate and save a Signal Event Report for a given list of signals over an explicit time window or the GUI selected time range (cursor + predefined marker).
target: [waveform]
examples:
  - "Save signal event report to <output_report_filename> for <signal_names> from <start_time> to <end_time>."
  - "Save signal event report to <output_report_filename> for <signal_names> in selected time range."
---

## Steps
- 1. Use `signal_event_report()` to generate the report (it opens the FSDB if needed, configures the signal list, sets time range, and writes the output file).
- 2. Time range mapping:
- 2.a. If user says 'selected time range' (cursor + marker), set `use_selected_time_range=true` and do not provide `start_time/end_time`.
- 2.b. Otherwise, pass `start_time/end_time` directly. Plain numeric strings (e.g. "100") mean default time unit; time-with-unit strings (e.g. "1us", "10ns") are also supported (units: s/ms/us/ns/ps/fs/as).
- 3. If user specifies an output file name, pass it as `output_report_filename` (otherwise keep the default).
