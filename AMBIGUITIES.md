# AMBIGUITIES

Each item says what is unclear, the options, what I chose and why, and where the code or a test pins it down.
The ones that change a printed number come first.

## A. Ambiguities that change the numbers

### A1. Retroactive fees: does a back-valued entry trigger fees for earlier days?
The fee rule defines the closing balance as "all entries with value_date ≤ that day", so E7 (value date Day 2, arriving on Day 5) makes Day 2 negative after the fact. Options: (a) only ever look at the current day; (b) at each day close, re-check every earlier day.
**Chosen: (b).** Every day close walks Day 1 → today and charges any day that is negative and has no fee yet. Criteria 1 and 2 both describe a Day 2 fee assessed at the end of Day 5, which only (b) produces. Under (a), E7 would cause one fee on Day 5 and none on Day 2.
*Code:* `Ledger._assess_overdraft_fees`. *Test:* `test_c2_refused_e7_causes_three_fees_on_days_2_4_and_5`.

### A2. "Booked with value_date equal to the day assessed": the day charged, or the day the charge is made?
For a Day 2 fee charged during the Day 5 close, "the day assessed" can mean Day 2 or Day 5.
**Chosen: the day the fee is for (Day 2).** The entry is value-dated Day 2 and booked on Day 5 (`booked_day=5`). Value-dating it Day 5 would make the Day 2 fee land on the Day 5 balance and change the cascade in A3.

### A3. Fee cascade order
A fee value-dated Day 2 lowers the balance of every later day. If days were checked in any order, or all at once, the result could differ.
**Chosen: oldest day first, with each fee counted before the next day is checked.** Here it makes no difference: Day 3 is 5.00 with the Day 2 fee counted and 30.00 without it, positive either way. The order is still fixed so the result does not depend on luck. *Test:* `test_c2_day3_escapes_a_fee_only_because_the_day2_fee_counts_first`.

### A4. Are fees ever refunded when a day turns positive again?
After E9, Days 2, 4 and 5 are positive again. The brief says when a fee is assessed but never when one is refunded.
**Chosen: no automatic refund. A fee once assessed is final.** "Assessed once per day" is satisfied, and refund policy (who caused the error, full or partial refund) is a business decision I should not invent. This is the design's weakest point. The one failing test (`tests/test_known_failure.py`) is about exactly this, and REJECTED.md, criterion 6, depends on it.

### A5. Interest: closing balance as known that night, or restated by value date?
The interest rule says "closing ledger balance" with no definition; the fee rule defines the same phrase as value-dated. Options: (a) accrue each night on the balance known then, never revisit; (b) restate earlier days' accruals when back-valued entries arrive.
**Chosen: (b), with adjustment records.** It reads the same phrase the same way in both rules, and value dates exist precisely so interest is computed from the right date. Each close recomputes every earlier day's rounded accrual and books only the difference as a new `Accrual` record (no record is edited). Under (a), ACC-001 would capitalize 0.10+0.10+0.26+0.19+0+0.16 = 0.81 and ACC-002 0.004. Under (b) they are 0.93 and 0.008.
*Code:* `Ledger._accrue_interest`. *Test:* `test_daily_accruals_follow_final_value_dated_balances`.

### A6. E10 is labelled Day 5 but listed after E9 (Day 6)
"Replayed in this order", but the order and the day labels disagree. Options: (a) sort by day label; (b) keep stream order and treat E10 as late; (c) reject E10 as out of sequence.
**Chosen: (b).** Stream order is arrival order. By the time E10 arrives, Day 5 is closed, and a closed day cannot be booked into. E10 is booked on Day 6 with value date Day 5 kept and a `[late: …]` note in the report. (c) would lose a customer's money; (a) rewrites the order the brief says to keep. Because interest is value-dated (A5), the final numbers are the same under (a) and (b): ACC-002 still earns interest for Day 5. Only the Day 5 snapshot differs (0.000 as known that night).
*Code:* `replay`, `Ledger._with_late_note`. *Test:* `test_e10_arrives_late_and_keeps_its_value_date`.

### A7. "Three equal instalments" of BHD 10.000
At 3 decimals, 10.000 / 3 cannot be split into three equal amounts.
**Chosen: 3.334, 3.333, 3.333.** The split works in whole fils, and the leftover fils goes to the first instalment. All three are value-dated Day 5 and posted together; nothing says they are spread over days. See REJECTED.md, criterion 7.

### A8. Which balance does an authorization check against, and when?
"Available balance = ledger balance − active holds", but which ledger balance: as at the moment of the request, or at day end? Does a same-day debit that arrived earlier count?
**Chosen: at the moment of the request, using every entry posted so far with value date ≤ the current business day, fees included.** E7 arrives before E8 on Day 5, so E8 sees −155.00 and Auth-B is declined. The decision is never revisited: E9 does not resurrect Auth-B.

### A9. Order of steps inside a day close
**Chosen:** detect restated days → fees (oldest day first) → interest → (Day 6 only) capitalize. Fees and interest on the same day cannot interact, because a fee needs a negative balance and interest a positive one. The capitalization credit is value-dated Day 6 and comes last, so it earns no interest inside the window. The Day 6 closing balance shown (390.93) includes it.

### A10. Rounding mode and rounding point
Not specified. **Chosen:** half-up, once per account per day on the accrual amount, never on the rate. See NUMBERS.md for why, and for the 0.92 vs 0.93 difference if you round only once at the end.

## B. Ambiguities about rules and lifecycle

### B1. What is the "Day" column?
**Chosen: the business day the event is booked on.** `value_date` is the day it counts from. `Entry.booked_day` and `Entry.value_date` record both.

### B2. When does a day close?
The stream has no "end of day" markers. **Chosen:** a day closes when the stream first shows an event for a later day, and the remaining days close at the end of the stream. So Day 5 closes when E9 (Day 6) arrives.

### B3. Can booked debits overdraw?
Yes. The availability check in the brief applies to authorizations only. E2 and E7 are booked events and post regardless. Overdraft fees only make sense if debits can overdraw. There is no overdraft limit.

### B4. Do holds affect fees or interest?
No. Both rules say "ledger balance", and holds are not ledger entries. *Test:* `test_holds_do_not_trigger_fees_or_reduce_interest`.

### B5. Partial settlement (Auth-A: hold 200.00, settles 185.00)
Is the 15.00 left on hold for a later settlement, or released? **Chosen:** one settlement per authorization; the authorization becomes SETTLED and the whole hold is released. Multi-clearing (several settlements against one authorization) is out of scope.

### B6. Does a settlement check available balance?
**Chosen: no.** The authorization already reserved the funds; the bank has committed to pay. Settlement posts even if it overdraws (`test_settlement_posts_even_if_it_overdraws`).

### B7. Settlement above the authorized amount
Not in the stream. **Chosen: reject, and keep the hold active.** This is the same principle as criterion 4: money only leaves against an authorization, and only up to its amount. Real card schemes allow tolerances (for example, tips), which I have not modelled. *Test:* `test_settlement_above_hold_rejected_and_hold_kept`.

### B8. Settlement with no authorization (Auth-Z)
Criterion 4 says reject, and I implemented that. The caveat: in real card processing a clearing record without a matching authorization (a "forced post" or offline transaction) usually cannot simply be refused. The scheme has already settled with the merchant's bank, so the issuer posts it and disputes it afterwards. The rejection is right inside this model, but it is not how I would ship it. See the architecture document.

### B9. Settlement against a declined or already-settled authorization
The authorization ID *is* in the ledger, so criterion 4's test ("ID not present") does not catch it. **Chosen: reject (status is not ACTIVE).** *Tests:* `test_settlement_against_declined_authorization_rejected`, `test_second_settlement_on_same_authorization_rejected`.

### B10. Is a declined authorization an "error"?
**Chosen: no.** It is a valid event with a business outcome. It is logged as applied, with state DECLINED and the available balance the decision was made on. Errors are reserved for events the ledger refused to process (E6) and conditions it could not handle (B13).

### B11. Authorizations never settled (Auth-B in the brief's wording)
"Auth-B is never settled inside the window." Auth-B is declined here, so it holds nothing. An *approved* authorization that never settles would hold funds forever: there is no expiry rule. Expiry is out of scope and covered in the architecture document.

### B12. Reversal semantics
**Chosen:** a reversal posts an equal and opposite entry for each entry of the original event (all instalments, if any) with the reversal's own value date. It never deletes or edits the original. Only CREDIT and DEBIT events can be reversed (not fees, settlements or other reversals), and only once. E9's value date (Day 2) equals E7's, so the reversal neutralises E7 for every day from Day 2.

### B13. Overdraft fee on a BHD account
The fee is defined in AED only. **Chosen:** no FX conversion. A negative BHD account produces an error line in the day close and no fee. It does not occur in this stream. *Test:* `test_negative_bhd_account_reported_not_charged`.

### B14. Input amounts with too many decimals
"Amounts stored and rounded to their own precision". Should AED 1.005 be rounded on the way in? **Chosen:** no, reject. Rounding is for amounts the ledger *computes* (interest, instalments). Silently rounding an amount someone sent is how money goes missing. *Test:* `test_amount_with_too_many_decimals`.

### B15. Future value dates, events outside the window, duplicates
Not covered by the brief. **Chosen:** reject a value date later than the current business day (no forward-dated entries), any event outside Day 1..6, any reuse of an event ID (the replay is idempotent per ID) and any reuse of an authorization ID. Each rejection leaves balances unchanged (`InvalidInput` tests).

### B16. What "closing ledger balance per day" means in the printout
After back-valuation, "Day 2's closing balance" has more than one true value, depending on when you ask. **Chosen:** print both. Each day block shows the balance as known at that day's close (with any restated earlier days listed). The final summary shows every day restated with everything known at the end of Day 6.

### B17. Append-only: what exactly is immutable?
**Chosen:** event records, ledger entries and accrual records are frozen and only ever appended. Authorization *state* is a projection (current status per auth ID). Settling replaces the frozen object with a new one; the events that caused the change stay in the log. Accessors return tuples, so callers cannot mutate history.

### B18. Interest on a zero balance, or on Day 1 before any credit
"Positive balances only": zero earns nothing. Opening balances are zero, so nothing accrues before E1.
