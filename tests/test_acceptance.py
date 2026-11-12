"""The brief's acceptance criteria, replayed against the real event stream.

Criteria that REJECTED.md refuses are tested for what actually happens, so
each refusal is backed by a passing test that shows the true behaviour.
"""

import dataclasses
import unittest
from decimal import Decimal

from ledger.core import AuthStatus, EntryType, Ledger, replay
from ledger.scenario import ACCOUNTS, EVENTS

D = Decimal


def replay_until(event_id: str) -> Ledger:
    """Replay the stream up to and including one event, without the final closes."""
    ledger = Ledger(ACCOUNTS)
    for event in EVENTS:
        while ledger.business_day < event.day:
            ledger.close_day()
        ledger.submit(event)
        if event.event_id == event_id:
            return ledger
    raise ValueError(event_id)


class AcceptanceCriteria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = replay(ACCOUNTS, EVENTS)
        cls.closes = {close.day: close for close in cls.ledger.day_closes()}

    # Criterion 1 (accepted)
    def test_c1_day2_closing_balance_at_end_of_day5_before_fees_is_minus_370(self):
        day5 = self.closes[5]
        restated = {(r.account_id, r.day): r for r in day5.restatements}
        self.assertEqual(restated[("ACC-001", 2)].restated, D("-370.00"))
        self.assertEqual(restated[("ACC-001", 2)].previous, D("250.00"))

    def test_c1_same_figure_read_directly_before_day5_close(self):
        ledger = replay_until("E8")
        self.assertEqual(ledger.closing_balance("ACC-001", 2), D("-370.00"))
        self.assertEqual(ledger.fees("ACC-001"), ())

    # Criterion 2 (refused: E7 causes three fees, not one)
    def test_c2_refused_e7_causes_three_fees_on_days_2_4_and_5(self):
        fees = self.ledger.fees("ACC-001")
        self.assertEqual([f.value_date for f in fees], [2, 4, 5])
        self.assertEqual({f.amount for f in fees}, {D("-25.00")})
        self.assertEqual({f.booked_day for f in fees}, {5})

    def test_c2_day3_escapes_a_fee_only_because_the_day2_fee_counts_first(self):
        history = {(a, d): b for a, d, b in self.closes[5].balance_history}
        self.assertEqual(history[("ACC-001", 3)], D("5.00"))  # -370 - 25 + 400

    def test_no_fees_before_e7_arrived(self):
        for day in (1, 2, 3, 4):
            self.assertEqual(self.closes[day].fees, ())

    # Criterion 3 (accepted)
    def test_c3_auth_a_settlement_accepted_and_hold_released(self):
        auth = self.ledger.authorization("Auth-A")
        self.assertIs(auth.status, AuthStatus.SETTLED)
        self.assertEqual(auth.settled_amount, D("185.00"))
        self.assertEqual(auth.released_amount, D("15.00"))
        settlements = [e for e in self.ledger.entries("ACC-001") if e.entry_type is EntryType.SETTLEMENT]
        self.assertEqual([(e.amount, e.value_date) for e in settlements], [(D("-185.00"), 4)])

    # Criterion 4 (accepted, with the forced-post caveat in AMBIGUITIES.md)
    def test_c4_auth_z_settlement_rejected_and_no_funds_leave(self):
        record = next(r for r in self.ledger.event_log() if r.event.event_id == "E6")
        self.assertFalse(record.applied)
        self.assertEqual([e for e in self.ledger.entries() if e.source_event_id == "E6"], [])
        self.assertIsNone(self.ledger.authorization("Auth-Z"))
        self.assertEqual(self.closes[4].closing_balances[0], ("ACC-001", D("465.00")))

    # Criterion 5 (premise false in this stream: Auth-B is declined)
    def test_c5_auth_b_is_declined_because_e7_arrived_first(self):
        auth = self.ledger.authorization("Auth-B")
        self.assertIs(auth.status, AuthStatus.DECLINED)
        self.assertEqual(auth.decided_on_available, D("-155.00"))

    # Criterion 6 (refused)
    def test_c6_refused_after_e9_fees_and_the_auth_b_decline_remain(self):
        self.assertEqual(len(self.ledger.fees("ACC-001")), 3)
        self.assertIs(self.ledger.authorization("Auth-B").status, AuthStatus.DECLINED)
        # without E7 the path would have been 465.00 at Day 4/5; it is 75.00 lower
        self.assertEqual(self.ledger.closing_balance("ACC-001", 5), D("390.00"))
        # history still shows E7 and its reversal side by side
        sources = [e.source_event_id for e in self.ledger.entries("ACC-001")]
        self.assertIn("E7", sources)
        self.assertIn("E9", sources)

    def test_e9_restores_the_debit_itself(self):
        reversal = [e for e in self.ledger.entries("ACC-001") if e.entry_type is EntryType.REVERSAL]
        self.assertEqual([(e.amount, e.value_date, e.booked_day) for e in reversal], [(D("620.00"), 2, 6)])

    # Criterion 7 (refused)
    def test_c7_refused_instalments_are_3334_3333_3333(self):
        parts = [e.amount for e in self.ledger.entries("ACC-002") if e.source_event_id == "E10"]
        self.assertEqual(parts, [D("3.334"), D("3.333"), D("3.333")])
        self.assertEqual(sum(parts), D("10.000"))

    def test_e10_arrives_late_and_keeps_its_value_date(self):
        parts = [e for e in self.ledger.entries("ACC-002") if e.source_event_id == "E10"]
        self.assertEqual({(e.booked_day, e.value_date) for e in parts}, {(6, 5)})

    # Criterion 8 (refused: there is never a remainder)
    def test_c8_refused_rounded_daily_accruals_equal_capitalized_total(self):
        for account_id, expected in (("ACC-001", D("0.93")), ("ACC-002", D("0.008"))):
            daily = [self.ledger.daily_accrual(account_id, d) for d in range(1, 7)]
            capitalized = [e.amount for e in self.ledger.entries(account_id) if e.entry_type is EntryType.INTEREST]
            self.assertEqual(capitalized, [expected])
            self.assertEqual(sum(daily), expected)

    def test_daily_accruals_follow_final_value_dated_balances(self):
        daily = [self.ledger.daily_accrual("ACC-001", d) for d in range(1, 7)]
        self.assertEqual(daily, [D(x) for x in ("0.10", "0.09", "0.25", "0.17", "0.16", "0.16")])

    # End state and the append-only rule
    def test_final_balances(self):
        self.assertEqual(self.ledger.closing_balance("ACC-001", 6), D("390.93"))
        self.assertEqual(self.ledger.closing_balance("ACC-002", 6), D("10.008"))

    def test_every_amount_is_held_at_its_currency_precision(self):
        exponent = {"ACC-001": -2, "ACC-002": -3}
        for entry in self.ledger.entries():
            self.assertEqual(entry.amount.as_tuple().exponent, exponent[entry.account_id], entry)

    def test_records_are_frozen_and_history_is_returned_as_copies(self):
        entry = self.ledger.entries()[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            entry.amount = D("0")
        record = self.ledger.event_log()[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.applied = False
        self.assertIsInstance(self.ledger.entries(), tuple)
        self.assertIsInstance(self.ledger.event_log(), tuple)

    def test_every_event_is_logged_once_in_stream_order(self):
        self.assertEqual([r.event.event_id for r in self.ledger.event_log()], [e.event_id for e in EVENTS])

    def test_entries_only_grow_during_the_replay(self):
        ledger = Ledger(ACCOUNTS)
        snapshots = []
        for event in EVENTS:
            while ledger.business_day < min(event.day, 6):
                ledger.close_day()
                snapshots.append(ledger.entries())
            ledger.submit(event)
            snapshots.append(ledger.entries())
        for earlier, later in zip(snapshots, snapshots[1:]):
            self.assertEqual(later[:len(earlier)], earlier)


if __name__ == "__main__":
    unittest.main()
