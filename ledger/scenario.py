"""The accounts and event stream from the brief, in the order given there.

Note E10: it belongs to Day 5 but is listed after E9 (Day 6). The replay keeps
the listed order, so E10 arrives after Day 5 has closed. See AMBIGUITIES.md.
"""

from decimal import Decimal

from ledger.core import Account, Event, EventType

ACCOUNTS = (
    Account("ACC-001", "AED", Decimal("0.00")),
    Account("ACC-002", "BHD", Decimal("0.000")),
)

EVENTS = (
    Event("E1", 1, EventType.CREDIT, "ACC-001", "AED", Decimal("1200.00"), value_date=1),
    Event("E2", 1, EventType.DEBIT, "ACC-001", "AED", Decimal("950.00"), value_date=1),
    Event("E3", 2, EventType.AUTHORIZATION, "ACC-001", "AED", Decimal("200.00"), value_date=2, auth_id="Auth-A"),
    Event("E4", 3, EventType.CREDIT, "ACC-001", "AED", Decimal("400.00"), value_date=3),
    Event("E5", 4, EventType.SETTLEMENT, "ACC-001", "AED", Decimal("185.00"), value_date=4, auth_id="Auth-A"),
    Event("E6", 4, EventType.SETTLEMENT, "ACC-001", "AED", Decimal("180.00"), value_date=4, auth_id="Auth-Z"),
    Event("E7", 5, EventType.DEBIT, "ACC-001", "AED", Decimal("620.00"), value_date=2),
    Event("E8", 5, EventType.AUTHORIZATION, "ACC-001", "AED", Decimal("90.00"), value_date=5, auth_id="Auth-B"),
    Event("E9", 6, EventType.REVERSAL, "ACC-001", "AED", value_date=2, reverses="E7"),
    Event("E10", 5, EventType.CREDIT, "ACC-002", "BHD", Decimal("10.000"), value_date=5, instalments=3),
)
