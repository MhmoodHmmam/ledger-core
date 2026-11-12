"""THE ONE DELIBERATELY FAILING TEST.

It asserts a property a bank would want and this design does not have. It is
left failing on purpose so the gap is visible every time the suite runs, and
is not marked expectedFailure, which would hide it as a pass.
"""

import unittest
from decimal import Decimal

from ledger.core import replay
from ledger.scenario import ACCOUNTS, EVENTS


class KnownDesignGap(unittest.TestCase):
    def test_fees_caused_only_by_a_reversed_debit_are_refunded(self):
        ledger = replay(ACCOUNTS, EVENTS)

        # WHAT IT EXPECTS: E7 (AED 620.00, back-valued to Day 2) is the only reason
        # ACC-001 went negative on Days 2, 4 and 5. E9 reverses E7 in full, with the
        # same value date. After that, the restated closing balances for those days
        # are 225.00, 415.00 and 390.00, all positive, so the condition that charged
        # the fees ("that day's closing ledger balance is negative") no longer holds
        # for any of them. A customer would expect the AED 75.00 back.
        net_fees = -sum((fee.amount for fee in ledger.fees("ACC-001")), Decimal(0))

        # WHAT IT REVEALS: the design re-evaluates fees in one direction only. Every
        # day close walks back over all earlier days and *adds* a fee when a day
        # turns negative (that is how E7 produced three fees at the end of Day 5),
        # but nothing ever looks at a day that has turned positive again. A fee,
        # once assessed, is final. Interest does not have this flaw: accruals are
        # re-evaluated in both directions through adjustment records, so the design
        # is internally inconsistent here.
        #
        # WHY IT WAS LEFT LIKE THIS: the brief defines when a fee is assessed but
        # not when one is refunded, and refunding is a customer-remediation policy
        # (full refund? only when the bank caused the error? within what time?).
        # Inventing one would have made criterion 6 ("after E9 ... fees return to
        # their pre-E7 values") look half-true. The fix would be a FEE_REVERSAL
        # entry, posted at day close when a fee's value day is no longer negative,
        # never a deletion of the original fee entry.
        #
        # ACTUAL RESULT: 75.00 (three fees, Days 2, 4 and 5). Expected 0.00.
        self.assertEqual(net_fees, Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
