# In-memory account ledger core

A value-dated, append-only account ledger in plain Python. It replays a fixed six-day event stream across two accounts, ACC-001 in AED and ACC-002 in BHD. It applies overdraft fees, daily interest, card authorization holds, settlements and reversals, and prints for each day the closing ledger balance, fee assessments, authorization states and errors.

There is no web layer, no persistence and no database. It uses the standard library only (`decimal`, `dataclasses`, `enum`, `unittest`), so there is nothing to install.

## Requirements

Python 3.10 or newer (it uses `X | None` type hints). Developed and run on Python 3.14.5.

## Run

From the repository root:

```bash
python replay.py
```

```bash
python -m unittest -v
```

**Expected test result: 52 tests, 1 failure.** The failure is deliberate:
`tests/test_known_failure.py::test_fees_caused_only_by_a_reversed_debit_are_refunded`.
It is annotated inline and explained in REJECTED.md, criterion 6. To run only the suite that should be green:

```bash
python -m unittest tests.test_acceptance tests.test_rules -v
```

## Reading the replay output

There is one block per day, then a summary.

```
DAY 5
Events processed        every event handled that day, in stream order, with its outcome
  E7   DEBIT ACC-001 620.00 vd2        vdN = value date. E7 arrives on Day 5 but counts from Day 2
       -> posted
Day close
  Back-valued days restated ...        earlier days whose balance changed since the last close,
    ACC-001 Day 2: 250.00 -> -370.00   measured BEFORE this close charged any fee
  Overdraft fee ... value-dated Day 2  fees charged at this close, with the day each one is for
  Interest accrual / adjustment        today's rounded accrual; "adjustment" = a correction to an
                                       earlier day after a back-valued entry (never an edit)
Closing ledger balance                 all entries value-dated on or before this day, as known at
                                       this close; "available" = ledger minus active holds
Authorizations                         state of every authorization at this close
Errors                                 events the ledger refused, and conditions it could not handle
```

- A `[late: …]` note means the event belongs to a day that had already closed when it arrived (E10). It is booked on the current day and keeps its value date.
- The **summary** restates every day using everything known at the end of Day 6. That is why Day 2 is −370.00 in the Day 5 block (before fees), −395.00 once the Day 2 fee is counted (the "from" value in the Day 6 block), and 225.00 in the summary after E9. Each is true at its moment.
- Headline results: ACC-001 ends at **AED 390.93**, after three overdraft fees (75.00) and 0.93 of capitalized interest. ACC-002 ends at **BHD 10.008**. Auth-A settled, Auth-B declined, Auth-Z rejected.

## Layout

| Path | What |
|---|---|
| `ledger/money.py` | Currency precision, half-up rounding, the exact instalment split |
| `ledger/core.py` | The ledger: records, validation, event handlers, day close (fees, interest, capitalization), `replay()` |
| `ledger/scenario.py` | The two accounts and the ten events, in the brief's order |
| `ledger/report.py` | Text report |
| `replay.py` | Entry point |
| `tests/test_acceptance.py` | Each acceptance criterion against the real stream |
| `tests/test_rules.py` | Boundaries, invalid input, nothing changed after a rejection |
| `tests/test_known_failure.py` | The one deliberately failing test |

## Design in five lines

1. Three record types: event records (what was submitted and what happened), entries (money movements) and accrual records. All are frozen and append-only. Balances are always computed from entries; nothing stores a running balance.
2. Every entry has a `booked_day` and a `value_date`. A day's closing balance means all entries value-dated on or before that day.
3. Each day close re-checks every earlier day, oldest first. It adds an overdraft fee to any day that has become negative and has no fee yet, and books an interest adjustment for any day whose rounded accrual has changed.
4. An authorization is approved only if ledger balance minus active holds stays at or above zero. The decision is made once, at request time.
5. Interest capitalized on Day 6 is the sum of the rounded daily accrual records, so it cannot leave a remainder.

## Documents

- [NUMBERS.md](NUMBERS.md): every constant and why, plus a derivation of every printed number
- [AMBIGUITIES.md](AMBIGUITIES.md): every ambiguity found and how it was resolved
- [REJECTED.md](REJECTED.md): the refused acceptance criteria, and approaches abandoned during the build
- [WORKLOG.md](WORKLOG.md): timestamped log
- [docs/architecture.pdf](docs/architecture.pdf): Part 2, architecture and trade-offs (its source is `docs/architecture.html`)
