# WORKLOG

Times are local (UTC+02:00), taken from the shell clock when each entry was written.
The build was done in one AI-assisted session (Claude Code), which the brief permits.
Entries record what was actually done and decided at that point, including dead ends.

| Time | What happened |
|---|---|
| 2026-11-12 17:36 | Read the brief (Part 1 ledger core, Part 2 architecture PDF). Empty folder created. |
| 2026-11-12 17:46 | Checked tools: Python 3.14.5, git 2.56, no pandoc/reportlab. Decided: Python standard library only (`decimal`, `dataclasses`, `unittest`), no third-party packages, so the suite runs on a bare Python install. |
| 2026-11-12 17:48 | Hand-replayed the stream on paper before writing code. Day 2 closing balance after E7 is 1,200.00 − 950.00 − 620.00 = −370.00. Retroactive fees at end of Day 5 cascade: Day 2 (−370.00), Day 3 no fee (−395.00 + 400.00 = 5.00), Day 4 (5.00 − 185.00 = −180.00), Day 5 (−205.00). So E7 causes three fees, not one. Auth-B is declined: available at E8 is −155.00, −245.00 after the hold. 3 × 3.334 = 10.002, not 10.000. Initial verdicts: criteria 2, 6, 7, 8 are wrong. |
| 2026-11-12 17:48 | `git init`. |
