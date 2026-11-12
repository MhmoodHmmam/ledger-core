# NUMBERS

Part 1 lists every constant in the code, what it is and why it has that value and not, say, half of it.
Part 2 derives every number the replay prints, so each can be checked by hand.

## 1. Constants

| Constant | Value | Where | Why this value and not half it |
|---|---|---|---|
| `FIRST_DAY` | `1` | `ledger/core.py` | The window starts on Day 1. Days are plain integers. There is no calendar, so there are no weekends or holidays. |
| `LAST_DAY` | `6` | `ledger/core.py` | The window is Day 1 to Day 6 inclusive, and interest capitalizes at the end of Day 6. With 3 the replay would stop before E7 and miss the whole back-valuation story. Events dated outside 1..6 are rejected. |
| `OVERDRAFT_FEE["AED"]` | `Decimal("25.00")` | `ledger/core.py` | Set by the brief. It is a flat amount per overdrawn day, not a percentage, so it does not depend on how far below zero the account is: −0.01 and −370.00 both cost 25.00. Half (12.50) would just be wrong. It is written to 2 decimals so it has AED precision from the start. |
| `OVERDRAFT_FEE["BHD"]` | *(absent)* | `ledger/core.py` | The brief gives an AED fee and no FX rule. Turning 25 AED into BHD needs a rate and a rate date, and I have neither. A negative BHD account is reported as an error and not charged. That never happens in this stream. |
| `DAILY_INTEREST_RATE` | `Decimal("0.0004")` | `ledger/core.py` | 0.04% per day is 0.04 / 100 = 0.0004 as a fraction. The usual slip is a factor of 100, not 2: `0.04` would be 4% a day. Half (0.0002) would halve every accrual: ACC-001 would capitalize about 0.47, not 0.93. It is a Decimal string, so the rate is exact (float 0.0004 is not). It is a simple daily rate, no day-count convention: about 14.6% a year, simple. |
| `MINOR_UNITS["AED"]` | `2` | `ledger/money.py` | ISO 4217: 1 dirham = 100 fils. Given by the brief. |
| `MINOR_UNITS["BHD"]` | `3` | `ledger/money.py` | ISO 4217: 1 dinar = 1,000 fils. Given by the brief. With 2, the BHD 0.004 daily accrual would round to 0.00 and ACC-002 would earn nothing. |
| `ROUNDING` | `ROUND_HALF_UP` | `ledger/money.py` | **My choice.** Exactly half a minor unit rounds away from zero (0.005 → 0.01). I picked it over banker's rounding (`ROUND_HALF_EVEN`) because a customer checking by hand expects it. No accrual in this stream lands on an exact half (0.186, 0.166, 0.156 are not halves), so the choice changes no printed number. `test_interest_rounds_half_up` pins it with AED 12.50 × 0.0004 = 0.005 → 0.01. |
| Rounding point | per account, per day, per accrual | `Ledger._accrue_interest` | **My choice.** Each daily accrual is rounded on its own, and capitalization adds up the *rounded* values. That makes "rounded daily accruals sum exactly to the capitalized total" true by construction. The alternative was to sum unrounded accruals and round once. That gives 0.10+0.09+0.25+0.166+0.156+0.156 = 0.918 → 0.92, which is 0.01 away from the rounded daily sum of 0.93, and the rule then fails. |
| Instalment leftover | goes to the earliest instalments, 1 minor unit each | `split_evenly` | **My choice.** 10.000 BHD is 10,000 fils, and 10,000 / 3 = 3,333 remainder 1, so the first instalment gets the extra fils: 3.334, 3.333, 3.333. Any fixed position would do. First is deterministic and easy to state. No instalment differs from another by more than 1 fils. |
| Instalment count | `3` | `ledger/scenario.py` (E10) | Given by the brief. |
| Opening balances | `0.00` AED, `0.000` BHD | `ledger/scenario.py` | Given by the brief. Written at each currency's precision, so balances keep the right number of decimals even before the first entry. |
| Availability threshold | `>= 0` | `Ledger._authorize` | The brief says "remains at or above zero". Exactly zero is approved (`test_approved_when_available_lands_exactly_on_zero`); 0.01 short is declined. |
| Fee threshold | `< 0` | `Ledger._assess_overdraft_fees` | "Negative" is strictly below zero, so a 0.00 balance is not charged (`test_zero_balance_is_not_overdrawn`). |

Test-only numbers: `100.00`/`100.01` (the authorization boundary at exactly 0 and 1 fils short), `12.50`/`12.49` (exactly half a fils of interest, and just under), `200.01` (one fils above an authorized hold).

## 2. Every printed number, derived

ACC-001 (AED). "Restated" means the balance of all entries value-dated up to and including that day, as known at that moment.

| When | Event / step | Calculation | Result |
|---|---|---|---|
| Day 1 | E1, E2 | 0.00 + 1,200.00 − 950.00 | closing **250.00** |
| Day 1 close | interest | 250.00 × 0.0004 = 0.1000 | accrual **0.10** |
| Day 2 | E3 Auth-A 200.00 | available 250.00 − 200.00 = 50.00 ≥ 0 | **approved**, available **50.00** |
| Day 2 close | interest | 250.00 × 0.0004 (holds don't count) | **0.10** |
| Day 3 | E4 +400.00 | 250.00 + 400.00 | closing **650.00**, available **450.00** |
| Day 3 close | interest | 650.00 × 0.0004 = 0.26 | **0.26** |
| Day 4 | E5 settles Auth-A at 185.00 | 650.00 − 185.00; hold 200.00 released, 15.00 unused | closing **465.00**, available **465.00** |
| Day 4 | E6 Auth-Z 180.00 | no such authorization | **rejected**, nothing posted |
| Day 4 close | interest | 465.00 × 0.0004 = 0.186 | **0.19** |
| Day 5 | E7 −620.00, value date Day 2 | ledger 465.00 − 620.00 | **−155.00** |
| Day 5 | E8 Auth-B 90.00 | −155.00 − 90.00 = −245.00 < 0 | **declined** |
| Day 5 close | restated before fees | Day 2: 250.00 − 620.00 = **−370.00**; Day 3: −370.00 + 400.00 = 30.00; Day 4: 30.00 − 185.00 = −155.00 | |
| Day 5 close | fees, oldest day first | Day 2: −370.00 < 0 → fee → −395.00. Day 3: −395.00 + 400.00 = **5.00** → no fee. Day 4: 5.00 − 185.00 = −180.00 → fee → −205.00. Day 5: −205.00 → fee → **−230.00** | 3 fees, **75.00** |
| Day 5 close | interest adjustments | Day 2 0.10 → 0 (−0.10). Day 3 5.00 × 0.0004 = 0.002 → 0.00 (−0.26). Day 4 0.19 → 0 (−0.19). Day 5 0. | |
| Day 6 | E9 reverses E7, +620.00 value date Day 2 | Day 2: −395.00 + 620.00 = 225.00. Day 3: 625.00. Day 4: 415.00. Day 5: 390.00 | |
| Day 6 close | fees | every day ≥ 0, and Days 2/4/5 already carry a fee | none |
| Day 6 close | interest adjustments | Day 2 225.00 → 0.09; Day 3 625.00 → 0.25; Day 4 415.00 → 0.166 → 0.17; Day 5 390.00 → 0.156 → 0.16; Day 6 390.00 → **0.16** | |
| Day 6 close | capitalization | 0.10 + 0.09 + 0.25 + 0.17 + 0.16 + 0.16 | **0.93** |
| End | final balance | 1,200 − 950 + 400 − 185 − 620 + 620 − 75 + 0.93 | **390.93** |

ACC-002 (BHD).

| When | Calculation | Result |
|---|---|---|
| Days 1–5 closes | no entries yet (E10 has not arrived) | 0.000, no interest |
| Day 6 | E10 BHD 10.000 = 10,000 fils, 10,000 / 3 = 3,333 rem 1 | **3.334 + 3.333 + 3.333** = 10.000, value date Day 5, booked Day 6 |
| Day 6 close | Day 5 restated 0.000 → 10.000; 10.000 × 0.0004 = 0.004 for Day 5 and Day 6 | 0.004 + 0.004 = **0.008** |
| End | 10.000 + 0.008 | **10.008** |

Counterfactual, for criterion 6 (the same stream without E7 and E9): ACC-001 Days 1–5 are 250.00, 250.00, 650.00, 465.00, 465.00, there are no fees, interest is 0.10+0.10+0.26+0.19+0.19+0.19 = 1.03, the final balance is 466.03, and Auth-B is approved (available 465.00 → 375.00). The real final balance, 390.93, is 75.10 lower: 75.00 of fees plus 0.10 less interest.
