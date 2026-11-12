"""Rule-level tests on small hand-built ledgers: boundaries, invalid input and
'nothing changed after a failure'."""

import unittest
from decimal import Decimal

from ledger.core import Account, AuthStatus, Event, EventType, Ledger
from ledger.money import round_to_currency, split_evenly

D = Decimal
AED, BHD = "ACC-AED", "ACC-BHD"


def new_ledger() -> Ledger:
    return Ledger([Account(AED, "AED", D("0.00")), Account(BHD, "BHD", D("0.000"))])


def credit(event_id, amount, day=1, value_date=None, account=AED, currency="AED", **extra):
    return Event(event_id, day, EventType.CREDIT, account, currency, D(amount),
                 value_date=value_date or day, **extra)


def debit(event_id, amount, day=1, value_date=None, account=AED, currency="AED"):
    return Event(event_id, day, EventType.DEBIT, account, currency, D(amount), value_date=value_date or day)


def authorize(event_id, auth_id, amount, day=1):
    return Event(event_id, day, EventType.AUTHORIZATION, AED, "AED", D(amount), value_date=day, auth_id=auth_id)


def settle(event_id, auth_id, amount, day=1):
    return Event(event_id, day, EventType.SETTLEMENT, AED, "AED", D(amount), value_date=day, auth_id=auth_id)


def reverse(event_id, target, day=1, value_date=1):
    return Event(event_id, day, EventType.REVERSAL, AED, "AED", value_date=value_date, reverses=target)


class Authorizations(unittest.TestCase):
    def test_approved_when_available_lands_exactly_on_zero(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "100.00"))
        ledger.submit(authorize("A1", "Auth-1", "100.00"))
        self.assertIs(ledger.authorization("Auth-1").status, AuthStatus.ACTIVE)
        self.assertEqual(ledger.available_balance(AED), D("0.00"))

    def test_declined_when_one_fils_short(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "100.00"))
        ledger.submit(authorize("A1", "Auth-1", "100.01"))
        self.assertIs(ledger.authorization("Auth-1").status, AuthStatus.DECLINED)
        self.assertEqual(ledger.available_balance(AED), D("100.00"))

    def test_hold_reduces_available_but_not_ledger_balance(self):
        """Criterion 5's rule, on an authorization that is actually approved."""
        ledger = new_ledger()
        ledger.submit(credit("C1", "500.00"))
        ledger.submit(authorize("A1", "Auth-1", "90.00"))
        self.assertEqual(ledger.ledger_balance(AED), D("500.00"))
        self.assertEqual(ledger.available_balance(AED), D("410.00"))
        self.assertEqual(len(ledger.entries(AED)), 1)

    def test_holds_do_not_trigger_fees_or_reduce_interest(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "100.00"))
        ledger.submit(authorize("A1", "Auth-1", "100.00"))
        close = ledger.close_day()
        self.assertEqual(close.fees, ())
        self.assertEqual(ledger.daily_accrual(AED, 1), D("0.04"))

    def test_duplicate_authorization_id_rejected(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "500.00"))
        ledger.submit(authorize("A1", "Auth-1", "50.00"))
        record = ledger.submit(authorize("A2", "Auth-1", "60.00"))
        self.assertFalse(record.applied)
        self.assertEqual(ledger.available_balance(AED), D("450.00"))


class Settlements(unittest.TestCase):
    def setUp(self):
        self.ledger = new_ledger()
        self.ledger.submit(credit("C1", "300.00"))
        self.ledger.submit(authorize("A1", "Auth-1", "200.00"))

    def test_settlement_posts_even_if_it_overdraws(self):
        self.ledger.submit(debit("D1", "250.00"))
        record = self.ledger.submit(settle("S1", "Auth-1", "200.00"))
        self.assertTrue(record.applied)
        self.assertEqual(self.ledger.ledger_balance(AED), D("-150.00"))

    def test_second_settlement_on_same_authorization_rejected(self):
        self.ledger.submit(settle("S1", "Auth-1", "100.00"))
        record = self.ledger.submit(settle("S2", "Auth-1", "50.00"))
        self.assertFalse(record.applied)
        self.assertEqual(self.ledger.ledger_balance(AED), D("200.00"))

    def test_settlement_above_hold_rejected_and_hold_kept(self):
        record = self.ledger.submit(settle("S1", "Auth-1", "200.01"))
        self.assertFalse(record.applied)
        self.assertIs(self.ledger.authorization("Auth-1").status, AuthStatus.ACTIVE)
        self.assertEqual(self.ledger.ledger_balance(AED), D("300.00"))

    def test_settlement_against_declined_authorization_rejected(self):
        self.ledger.submit(authorize("A2", "Auth-2", "999.00"))
        record = self.ledger.submit(settle("S1", "Auth-2", "10.00"))
        self.assertFalse(record.applied)
        self.assertIn("DECLINED", record.message)


class Reversals(unittest.TestCase):
    def test_reversal_twice_is_rejected(self):
        ledger = new_ledger()
        ledger.submit(debit("D1", "50.00"))
        self.assertTrue(ledger.submit(reverse("R1", "D1")).applied)
        self.assertFalse(ledger.submit(reverse("R2", "D1")).applied)
        self.assertEqual(ledger.ledger_balance(AED), D("0.00"))

    def test_reversal_of_unknown_or_rejected_event_is_rejected(self):
        ledger = new_ledger()
        ledger.submit(debit("D1", "1.005"))  # rejected for precision
        self.assertFalse(ledger.submit(reverse("R1", "D1")).applied)
        self.assertFalse(ledger.submit(reverse("R2", "NOPE")).applied)
        self.assertEqual(ledger.entries(), ())

    def test_reversal_of_instalment_credit_reverses_every_part(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "10.000", account=BHD, currency="BHD", instalments=3))
        reversal = Event("R1", 1, EventType.REVERSAL, BHD, "BHD", value_date=1, reverses="C1")
        ledger.submit(reversal)
        self.assertEqual(ledger.ledger_balance(BHD), D("0.000"))
        self.assertEqual(len(ledger.entries(BHD)), 6)


class InvalidInput(unittest.TestCase):
    def assert_rejected_without_side_effects(self, ledger, event, fragment):
        before = ledger.entries()
        record = ledger.submit(event)
        self.assertFalse(record.applied)
        self.assertIn(fragment, record.message)
        self.assertEqual(ledger.entries(), before)

    def test_amount_with_too_many_decimals(self):
        self.assert_rejected_without_side_effects(new_ledger(), credit("C1", "1.005"), "more decimals")

    def test_bhd_accepts_three_decimals(self):
        ledger = new_ledger()
        self.assertTrue(ledger.submit(credit("C1", "1.005", account=BHD, currency="BHD")).applied)

    def test_zero_and_negative_amounts(self):
        ledger = new_ledger()
        self.assert_rejected_without_side_effects(ledger, credit("C1", "0.00"), "positive")
        self.assert_rejected_without_side_effects(ledger, credit("C2", "-5.00"), "positive")

    def test_currency_mismatch(self):
        self.assert_rejected_without_side_effects(new_ledger(), credit("C1", "5.000", currency="BHD"), "currency")

    def test_unknown_account(self):
        self.assert_rejected_without_side_effects(new_ledger(), credit("C1", "5.00", account="ACC-404"), "unknown")

    def test_duplicate_event_id(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "5.00"))
        self.assert_rejected_without_side_effects(ledger, credit("C1", "5.00"), "duplicate")
        self.assertEqual(ledger.ledger_balance(AED), D("5.00"))

    def test_future_value_date(self):
        self.assert_rejected_without_side_effects(new_ledger(), credit("C1", "5.00", value_date=2), "value date")

    def test_event_outside_window(self):
        self.assert_rejected_without_side_effects(new_ledger(), credit("C1", "5.00", day=7, value_date=1), "outside")

    def test_settlement_without_authorization_id(self):
        event = Event("S1", 1, EventType.SETTLEMENT, AED, "AED", D("5.00"), value_date=1)
        self.assert_rejected_without_side_effects(new_ledger(), event, "authorization id")

    def test_instalments_only_on_credits_and_debits(self):
        event = Event("A1", 1, EventType.AUTHORIZATION, AED, "AED", D("5.00"), value_date=1,
                      auth_id="Auth-1", instalments=2)
        self.assert_rejected_without_side_effects(new_ledger(), event, "instalments")


class FeesAndInterest(unittest.TestCase):
    def test_fee_assessed_once_per_day_across_repeated_closes(self):
        ledger = new_ledger()
        ledger.submit(debit("D1", "10.00"))
        ledger.close_day()  # Day 1: fee
        ledger.close_day()  # Day 2: balance still negative -> one new fee for Day 2 only
        self.assertEqual([f.value_date for f in ledger.fees(AED)], [1, 2])

    def test_zero_balance_is_not_overdrawn(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "10.00"))
        ledger.submit(debit("D1", "10.00"))
        self.assertEqual(ledger.close_day().fees, ())

    def test_negative_bhd_account_reported_not_charged(self):
        ledger = new_ledger()
        ledger.submit(debit("D1", "1.000", account=BHD, currency="BHD"))
        close = ledger.close_day()
        self.assertEqual(ledger.fees(BHD), ())
        self.assertEqual(len(close.errors), 1)
        self.assertIn("no overdraft fee is defined for BHD", close.errors[0])

    def test_no_interest_on_negative_balance(self):
        ledger = new_ledger()
        ledger.submit(debit("D1", "1000.00"))
        ledger.close_day()
        self.assertEqual(ledger.daily_accrual(AED, 1), D("0.00"))

    def test_interest_rounds_half_up(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "12.50"))  # 12.50 x 0.0004 = 0.005 exactly
        ledger.close_day()
        self.assertEqual(ledger.daily_accrual(AED, 1), D("0.01"))

    def test_interest_below_half_a_fils_rounds_to_zero(self):
        ledger = new_ledger()
        ledger.submit(credit("C1", "12.49"))  # 0.004996
        ledger.close_day()
        self.assertEqual(ledger.daily_accrual(AED, 1), D("0.00"))

    def test_day_close_after_window_is_refused(self):
        ledger = new_ledger()
        for _ in range(6):
            ledger.close_day()
        with self.assertRaises(RuntimeError):
            ledger.close_day()
        self.assertFalse(ledger.submit(credit("C1", "1.00", day=6, value_date=6)).applied)


class Money(unittest.TestCase):
    def test_split_sums_exactly_and_differs_by_at_most_one_minor_unit(self):
        for amount, parts, currency in ((D("10.000"), 3, "BHD"), (D("0.01"), 3, "AED"), (D("100.00"), 7, "AED")):
            split = split_evenly(amount, parts, currency)
            self.assertEqual(sum(split), amount)
            self.assertEqual(len(split), parts)
            self.assertLessEqual(max(split) - min(split), D(1).scaleb(-2 if currency == "AED" else -3))

    def test_split_into_one_part_is_the_amount(self):
        self.assertEqual(split_evenly(D("10.000"), 1, "BHD"), [D("10.000")])

    def test_round_to_currency(self):
        self.assertEqual(round_to_currency(D("0.1665"), "AED"), D("0.17"))
        self.assertEqual(round_to_currency(D("0.0045"), "BHD"), D("0.005"))


if __name__ == "__main__":
    unittest.main()
