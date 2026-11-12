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
| 2026-11-12 17:48 | Design decisions before code. Stream order is kept and E10 is treated as a late arrival (sorting by day label rejected). Interest is restated by value date with adjustment records; point-in-time accrual rejected because it reads "closing ledger balance" differently from the fee rule. Fees are re-checked back to Day 1 at each close, oldest first, and never refunded (no refund rule in the brief). |
| 2026-11-12 17:49 | Wrote `ledger/money.py` (Decimal, half-up, whole-fils split) and `ledger/core.py`. While writing, dropped the planned `fee_days` and `reversed` sets in favour of deriving both from the append-only records. Added the rule that an event dated after the current business day is rejected. |
| 2026-11-12 17:50 | First replay run. Output matched the hand replay: fees on Days 2/4/5 (75.00), Auth-B declined at −245.00, final ACC-001 390.93, ACC-002 10.008, interest 0.93 / 0.008. The report printed nothing for a day with no accrual, which looked like a missed accrual; changed it to print an explicit 0. Committed. |
| 2026-11-12 17:51 | Acceptance tests (one or more per criterion, refused criteria tested for actual behaviour) and rule tests (boundaries at exactly 0 and 1 fils short, invalid input with no side effects, half-up at exactly 0.005). 51 passing. Committed. |
| 2026-11-12 17:51 | Added the one failing test: fees caused only by E7 are not refunded after E9 (75.00 vs 0.00). Considered `expectedFailure` and rejected it, because it reports as a pass. Suite: 52 run, 1 failure. Committed. |
| 2026-11-12 17:54 | Ran a no-E7/E9 counterfactual to quantify criterion 6: final 466.03 vs 390.93 (75.00 fees + 0.10 interest), Auth-B would have been approved. Wrote NUMBERS.md, AMBIGUITIES.md, REJECTED.md, README. |
| 2026-11-12 17:56 | Part 2: wrote `docs/architecture.html` and rendered `docs/architecture.pdf` (3 pages, A4) with headless Edge, since no PDF library is installed and adding one was not worth it. Picked a per-account value-date index plus a dirty-from watermark as the cheapest scale fix, and a maker-checker back-valuation gate as the single pre-go-live control. Regulatory and scheme claims are marked [knowledge] because they were not checked against source documents in this session. Added `docs/decision-log.md`. |
