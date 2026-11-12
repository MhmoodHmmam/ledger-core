# Decision log

Source tags: **[source]** = checked against the installed Python by running it in this session; **[knowledge]** = from general knowledge, not checked against a document in this session.

## Part 1: ledger core
- Decision: Python standard library only. Money is `Decimal`, quantized per currency with `ROUND_HALF_UP`. Records are frozen dataclasses in append-only lists. Day close re-checks history by value date: fees are added only, interest is adjusted both ways.
- Rejected: floats (binary rounding error); third-party packages (nothing needed, and nothing to install for reviewers); sorting the stream by day label; point-in-time interest. Reasons in REJECTED.md, section 2.
- Sources:
  - [source] `decimal.Decimal.quantize` with `ROUND_HALF_UP` on Python 3.14.5: 0.005 → 0.01 and 0.1665 → 0.17, pinned by `test_interest_rounds_half_up` and `test_round_to_currency`.
  - [source] `dataclasses.FrozenInstanceError` raised on assignment to a frozen dataclass, pinned by `test_records_are_frozen_and_history_is_returned_as_copies`.
  - [knowledge] ISO 4217 minor units: AED 2, BHD 3 (also stated in the brief).

## Part 2: architecture document
- Decision: HTML source in `docs/architecture.html`, rendered to `docs/architecture.pdf` with headless Microsoft Edge (`--print-to-pdf`). No PDF library added.
- Sources:
  - [knowledge] Central Bank of the UAE consumer-protection framework (fair and disclosed fees); UAE VAT at 5% on fee-based financial services, with margin-based interest generally exempt; card-scheme practice on forced posts, clearing tolerances and authorization expiry periods. These claims are marked [knowledge] in the PDF and should be checked against the current regulation and scheme rules before anyone relies on them.
