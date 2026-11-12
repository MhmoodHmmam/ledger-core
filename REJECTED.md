# REJECTED

## 1. Acceptance criteria

The brief says some of the eight criteria are wrong. I checked each one against a hand replay (NUMBERS.md, part 2) and then against the code. **Four are refused (2, 6, 7, 8).** Two are accepted as stated (1, 3). Two are accepted with a qualification (4, 5).

| # | Criterion (short) | Verdict | Test |
|---|---|---|---|
| 1 | Day 2 balance at end of Day 5, before fees, is −370.00 | Accepted | `test_c1_*` |
| 2 | E7 causes exactly one fee, on Day 2 | **Refused** | `test_c2_refused_*` |
| 3 | Day 4 settlement of Auth-A accepted | Accepted | `test_c3_*` |
| 4 | Unmatched settlement rejected, no funds leave | Accepted, with a real-world caveat | `test_c4_*` |
| 5 | If Auth-B approved, hold hits available not ledger | Accepted as a rule; the premise is false | `test_c5_*`, `test_hold_reduces_available_but_not_ledger_balance` |
| 6 | After E9 balances and fees return to pre-E7 values | **Refused** | `test_c6_refused_*` |
| 7 | Each E10 instalment is BHD 3.334 | **Refused** | `test_c7_refused_*` |
| 8 | If accruals don't sum to the total, discard the remainder | **Refused** | `test_c8_refused_*` |

### Criterion 2, refused: "E7 causes exactly one overdraft fee to be assessed, on Day 2."
E7 causes **three** fees: Day 2, Day 4 and Day 5, all assessed at the end of Day 5.

- Day 2: 250.00 − 620.00 = −370.00 → fee → −395.00.
- Day 3: −395.00 + 400.00 = 5.00 → no fee.
- Day 4: 5.00 − 185.00 (Auth-A settlement) = −180.00 → fee → −205.00.
- Day 5: −205.00, with nothing else posted → fee → −230.00.

Without E7, Days 2 to 5 would be 250.00, 650.00, 465.00 and 465.00: no fees at all. So all three are caused by E7. The criterion only looks at E7's own value day and misses that a back-valued debit lowers every later day too. Day 3 escapes only because E4's 400.00 credit lifts it above zero. The only reading under which "exactly one" could hold is "no retroactive fees at all" (AMBIGUITIES A1, option a), and then that one fee would be on Day 5, not Day 2. The criterion is wrong under either reading.

### Criterion 6, refused: "After E9, all balances and fees return to their pre-E7 values."
Four separate reasons, any one of which is enough:

1. **Fees do not return.** The three AED 25.00 fees (75.00) were assessed on balances that were really negative at the time. The ledger is append-only, so they cannot be deleted. E9 reverses E7, not the fees. ACC-001 ends Day 5 at 390.00, against 465.00 without E7.
2. **Auth-B's decline does not return.** E8 was decided on an available balance of −155.00, which existed only because of E7. Without E7, Auth-B would have been approved with 465.00 available. An authorization decision is made once, at request time, and a later reversal does not re-run it.
3. **Interest does not return.** Days 2 to 5 carry fees, so their balances (and the interest on them) are lower than on the no-E7 path. ACC-001 capitalizes 0.93 instead of 1.03.
4. **"Return" is not something an append-only ledger does.** E7 and E9 both stay in history; balances are restored *by adding* an offsetting entry, not by going back.

The *debit itself* is fully neutralised: E9 posts +620.00 with value date Day 2 (`test_e9_restores_the_debit_itself`). The final balance is 390.93 against 466.03 on the no-E7 path, a gap of 75.10 (75.00 of fees plus 0.10 less interest). Whether the bank *should* refund those fees is a fair question, and it is the subject of the one failing test.

### Criterion 7, refused: "The three BHD instalments in E10 must each be BHD 3.334."
3 × 3.334 = 10.002, which is 0.002 more than the 10.000 credited. That creates 2 fils out of nothing and breaks the ledger's basic duty that entries add up to the event. The instalments are **3.334 + 3.333 + 3.333 = 10.000**. (Making all three 3.333 would lose 1 fils instead, which is just as wrong.) "Equal" cannot be exact at 3 decimals, so the split is as equal as the currency allows: no instalment differs from another by more than 1 fils.

### Criterion 8, refused: "If the rounded daily interest accruals do not sum to the capitalized total, the remainder is discarded."
This contradicts a non-negotiable rule: "The rounded daily accruals must sum exactly to the capitalized total." A rule that says what to do with a remainder assumes the two totals can differ. Discarding money silently is also exactly what a ledger must never do. In this design the capitalized amount is *defined* as the sum of the rounded daily accrual records, so no remainder can exist. `_capitalize_interest` raises an error if the two ever disagree, rather than discarding anything.

### Criterion 1, accepted: Day 2 at end of Day 5, before fees, is AED −370.00.
1,200.00 − 950.00 − 620.00 = −370.00. Auth-A's hold is not a ledger entry, and no fee had been assessed before the Day 5 close (every earlier close saw positive balances). The Day 5 close prints `ACC-001 Day 2: 250.00 -> -370.00` before any fee.

### Criterion 3, accepted: the Day 4 settlement of Auth-A must be accepted.
Auth-A was approved on Day 2 (available 250.00 − 200.00 = 50.00 ≥ 0) and is ACTIVE. 185.00 does not exceed the 200.00 hold. It settles; the hold is released and 15.00 of it was never used.

### Criterion 4, accepted with a qualification: an unmatched settlement is rejected and no funds leave.
Implemented: E6 (Auth-Z) is logged as rejected, no entry is posted, and the balance is unchanged. Two qualifications. (a) The criterion only covers IDs "not present". An ID that *is* present but declined or already settled must be rejected too, and the code does that (AMBIGUITIES B9). (b) In real card processing an issuer usually cannot refuse a clearing record; it posts it and disputes it (AMBIGUITIES B8). I accept the criterion as the rule *of this model*.

### Criterion 5, accepted as a rule, premise false: "If Auth-B is approved, its hold reduces available balance but not ledger balance."
As a general rule it is correct, and it is tested on an authorization that is approved. **In this stream Auth-B is not approved.** At E8, ledger balance is −155.00 (E7 arrived earlier the same day), there are no active holds, and −155.00 − 90.00 = −245.00 < 0. The sentence "Auth-B is never settled inside the window" invites the reader to assume an outstanding 90.00 hold. There is none.

## 2. Approaches abandoned mid-build

These were all considered in this session; the WORKLOG shows when. Some never reached code; that is noted.

1. **Sorting the stream by day label** so E10 lands on Day 5. Dropped before coding: the brief says "replayed in this order", and quietly reordering input is the kind of thing that hides a late-arrival problem in production. Replaced by late booking with value date kept (AMBIGUITIES A6).
2. **Point-in-time interest** (accrue each night, never revisit). This was the first and simplest idea. Dropped because it reads "closing ledger balance" differently in the interest rule than in the fee rule. It would capitalize 0.81, paying interest on Days 3 and 4 balances that the bank later knew were wrong, and ACC-002 would lose Day 5's interest only because E10 arrived late.
3. **Computing all interest once at capitalization** from the final balances. Same final numbers as the chosen approach, but there would be nothing to print per day, and it hides *when* each accrual changed. Replaced by daily accrual records plus adjustment records.
4. **Keeping a `fee_days` set and a `reversed_events` set** next to the entries. Dropped while writing `core.py`: both can be derived from the append-only records (`_has_fee` scans fee entries; the reversal check scans the event log). Every extra piece of mutable state is something that can disagree with the ledger.
5. **Logging a declined authorization as a rejected event.** Dropped: a decline is a valid outcome of a valid request, and lumping it in with "errors" would hide real processing errors such as E6.
6. **Accepting settlements larger than the hold** (as card schemes do with tips). Dropped as inconsistent with criterion 4's principle. Rejecting is the conservative choice inside a model with no tolerance rule.
7. **Marking the failing test `expectedFailure`.** Dropped: unittest then reports it as OK, and the brief asks for a failing test, not a hidden one.
8. **The report originally printed nothing** for a day with no accrual, so Day 5 (negative) looked as if interest had been forgotten. Changed during the first replay run to print an explicit 0 with "closing balance not positive".
