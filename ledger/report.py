"""Plain-text report of a replayed ledger: one block per day, then a summary."""

from decimal import Decimal

from ledger.core import FIRST_DAY, LAST_DAY, AuthStatus, EntryType, Ledger
from ledger.money import format_amount


def render(ledger: Ledger) -> str:
    currency = {a.account_id: a.currency for a in ledger.accounts()}

    def money(account_id, amount, signed=False):
        text = format_amount(amount, currency[account_id])
        return f"+{text}" if signed and amount > 0 else text

    lines: list[str] = []
    add = lines.append

    for close in ledger.day_closes():
        day = close.day
        add("=" * 78)
        add(f"DAY {day}")
        add("=" * 78)

        add("Events processed")
        records = [r for r in ledger.event_log() if r.processed_day == day]
        if not records:
            add("  (none)")
        for record in records:
            event = record.event
            amount = money(event.account_id, event.amount) if event.amount is not None else ""
            ref = event.auth_id or (f"reverses {event.reverses}" if event.reverses else "")
            add(f"  {event.event_id:<4} {event.event_type.value:<13} {event.account_id} "
                f"{amount:>10} vd{event.value_date} {ref}".rstrip())
            add(f"       -> {record.message}")

        add("Day close")
        if close.restatements:
            add("  Back-valued days restated (before any fee this close):")
            for r in close.restatements:
                add(f"    {r.account_id} Day {r.day}: {money(r.account_id, r.previous)} "
                    f"-> {money(r.account_id, r.restated)}")
        if close.fees:
            for fee in close.fees:
                add(f"  Overdraft fee  {fee.account_id} {money(fee.account_id, fee.amount)} "
                    f"value-dated Day {fee.value_date}")
        else:
            add("  Overdraft fees: none")
        accrued_today = {a.account_id for a in close.accruals if a.for_day == day}
        for account_id in currency:
            if account_id not in accrued_today:
                add(f"  Interest accrual    {account_id} Day {day}: {money(account_id, Decimal(0))} "
                    f"(closing balance not positive)")
        for accrual in close.accruals:
            kind = "accrual" if accrual.for_day == day else "adjustment"
            add(f"  Interest {kind:<10} {accrual.account_id} Day {accrual.for_day}: "
                f"{money(accrual.account_id, accrual.amount, signed=True)}")
        for entry in close.capitalizations:
            add(f"  Interest capitalized {entry.account_id} {money(entry.account_id, entry.amount, signed=True)} "
                f"value-dated Day {entry.value_date}")

        add(f"Closing ledger balance (entries value-dated Day {day} or earlier)")
        available = dict(close.available_balances)
        for account_id, balance in close.closing_balances:
            add(f"  {account_id} {currency[account_id]} {money(account_id, balance):>10}   "
                f"available {money(account_id, available[account_id]):>10}")

        add("Authorizations")
        if not close.authorizations:
            add("  (none)")
        for auth in close.authorizations:
            detail = f"hold {money(auth.account_id, auth.hold_amount)}"
            if auth.status is AuthStatus.SETTLED:
                detail = (f"settled {money(auth.account_id, auth.settled_amount)}, "
                          f"released {money(auth.account_id, auth.released_amount)} unused")
            elif auth.status is AuthStatus.DECLINED:
                detail = (f"requested {money(auth.account_id, auth.hold_amount)} on available "
                          f"{money(auth.account_id, auth.decided_on_available)}")
            add(f"  {auth.auth_id:<7} {auth.account_id} {auth.status.value:<8} {detail}")

        add("Errors")
        errors = [f"{r.event.event_id}: {r.message}" for r in records if not r.applied] + list(close.errors)
        if not errors:
            add("  (none)")
        for error in errors:
            add(f"  {error}")
        add("")

    add("=" * 78)
    add("SUMMARY AT END OF DAY 6 (all balances restated by value date)")
    add("=" * 78)
    for account in ledger.accounts():
        account_id = account.account_id
        add(f"{account_id} ({account.currency})")
        add("  Day  closing balance  daily interest (rounded)")
        for day in range(FIRST_DAY, LAST_DAY + 1):
            add(f"  {day:>3}  {money(account_id, ledger.closing_balance(account_id, day)):>15}  "
                f"{money(account_id, ledger.daily_accrual(account_id, day)):>10}")
        accrued = sum((ledger.daily_accrual(account_id, d) for d in range(FIRST_DAY, LAST_DAY + 1)), Decimal(0))
        capitalized = sum((e.amount for e in ledger.entries(account_id) if e.entry_type is EntryType.INTEREST),
                          Decimal(0))
        fees = ledger.fees(account_id)
        fee_total = -sum((f.amount for f in fees), Decimal(0))
        fee_days = ", ".join(f"Day {f.value_date}" for f in fees) or "none"
        add(f"  Sum of rounded daily accruals: {money(account_id, accrued)}; "
            f"capitalized: {money(account_id, capitalized)}")
        add(f"  Overdraft fees: {len(fees)} totalling {money(account_id, fee_total)} ({fee_days})")
        add(f"  Final ledger balance after capitalization: "
            f"{money(account_id, ledger.closing_balance(account_id, LAST_DAY))}")
    add("")
    add("Day 6 closing balances include the capitalization credit; Day 6 interest was")
    add("accrued on the balance before that credit.")
    return "\n".join(lines)
