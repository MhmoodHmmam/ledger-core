"""In-memory account ledger core.

Three kinds of state, kept deliberately apart:

* ``EventRecord`` – every submitted event and what happened to it (applied or
  rejected, with the reason). Append-only.
* ``Entry`` – every movement of money, value-dated. Append-only. Balances are
  always *computed* from entries; no running balance is stored anywhere.
* ``Authorization`` – the current state of each card authorization. This is a
  projection: when an authorization settles, the old frozen object is replaced
  by a new one. The events that caused the change stay in the event log.

All records are frozen dataclasses and every accessor returns a tuple, so
callers cannot mutate or delete history.

Days are integers 1..6. ``business_day`` is the day the ledger is currently
booking on; ``value_date`` is the day an entry counts from for balances, fees
and interest. They differ for back-valued entries such as E7.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from ledger.money import (
    format_amount,
    has_currency_precision,
    is_supported,
    round_to_currency,
    split_evenly,
)

FIRST_DAY = 1
LAST_DAY = 6

# Overdraft fee per account currency. The rule only defines an AED fee; there is
# no BHD amount and no FX rule, so a negative BHD account is reported as an
# error instead of being charged a made-up conversion. See AMBIGUITIES.md.
OVERDRAFT_FEE = {"AED": Decimal("25.00")}

# 0.04% per day, as a fraction. Applied to positive closing balances only.
DAILY_INTEREST_RATE = Decimal("0.0004")

ZERO = Decimal(0)


class EventType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    AUTHORIZATION = "AUTHORIZATION"
    SETTLEMENT = "SETTLEMENT"
    REVERSAL = "REVERSAL"


class EntryType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    SETTLEMENT = "SETTLEMENT"
    REVERSAL = "REVERSAL"
    OVERDRAFT_FEE = "OVERDRAFT_FEE"
    INTEREST = "INTEREST"


class AuthStatus(str, Enum):
    ACTIVE = "ACTIVE"      # approved, hold reduces available balance
    SETTLED = "SETTLED"    # matched by a settlement, hold released
    DECLINED = "DECLINED"  # refused at request time, never held anything


@dataclass(frozen=True)
class Account:
    account_id: str
    currency: str
    opening_balance: Decimal


@dataclass(frozen=True)
class Event:
    event_id: str
    day: int                        # business day the event belongs to
    event_type: EventType
    account_id: str
    currency: str
    amount: Decimal | None = None
    value_date: int | None = None
    auth_id: str | None = None      # AUTHORIZATION and SETTLEMENT
    reverses: str | None = None     # REVERSAL: the event_id being reversed
    instalments: int = 1            # CREDIT and DEBIT may be posted in parts


@dataclass(frozen=True)
class EventRecord:
    event: Event
    processed_day: int
    applied: bool
    message: str


@dataclass(frozen=True)
class Entry:
    sequence: int
    account_id: str
    entry_type: EntryType
    amount: Decimal                 # signed: credits positive, debits negative
    value_date: int
    booked_day: int
    source_event_id: str | None     # None for system entries (fees, interest)


@dataclass(frozen=True)
class Authorization:
    auth_id: str
    account_id: str
    hold_amount: Decimal
    requested_day: int
    status: AuthStatus
    decided_on_available: Decimal   # available balance the decision was made on
    settled_amount: Decimal | None = None
    released_amount: Decimal | None = None
    settled_day: int | None = None


@dataclass(frozen=True)
class Accrual:
    """One rounded interest accrual record. Later records for the same day are
    adjustments: the day's accrual is the sum of its records."""

    account_id: str
    for_day: int
    amount: Decimal
    computed_on_day: int


@dataclass(frozen=True)
class Restatement:
    """A past day's closing balance that changed because of a back-valued entry,
    measured before this close assessed any fee."""

    account_id: str
    day: int
    previous: Decimal
    restated: Decimal


@dataclass(frozen=True)
class DayClose:
    day: int
    restatements: tuple[Restatement, ...]
    fees: tuple[Entry, ...]
    accruals: tuple[Accrual, ...]
    capitalizations: tuple[Entry, ...]
    closing_balances: tuple[tuple[str, Decimal], ...]     # value_date <= day
    available_balances: tuple[tuple[str, Decimal], ...]
    balance_history: tuple[tuple[str, int, Decimal], ...]  # every day <= this one
    authorizations: tuple[Authorization, ...]
    errors: tuple[str, ...]


class Ledger:
    def __init__(self, accounts: tuple[Account, ...] | list[Account]):
        self._accounts = {account.account_id: account for account in accounts}
        self._event_log: list[EventRecord] = []
        self._entries: list[Entry] = []
        self._accruals: list[Accrual] = []
        self._authorizations: dict[str, Authorization] = {}
        self._day_closes: list[DayClose] = []
        self.business_day = FIRST_DAY
        self.window_closed = False

    # ------------------------------------------------------------------ reads

    def accounts(self) -> tuple[Account, ...]:
        return tuple(self._accounts.values())

    def event_log(self) -> tuple[EventRecord, ...]:
        return tuple(self._event_log)

    def entries(self, account_id: str | None = None) -> tuple[Entry, ...]:
        return tuple(e for e in self._entries if account_id in (None, e.account_id))

    def accruals(self, account_id: str | None = None) -> tuple[Accrual, ...]:
        return tuple(a for a in self._accruals if account_id in (None, a.account_id))

    def authorizations(self) -> tuple[Authorization, ...]:
        return tuple(self._authorizations.values())

    def authorization(self, auth_id: str) -> Authorization | None:
        return self._authorizations.get(auth_id)

    def day_closes(self) -> tuple[DayClose, ...]:
        return tuple(self._day_closes)

    def closing_balance(self, account_id: str, day: int) -> Decimal:
        """Ledger balance counting every entry with value_date <= day."""
        account = self._accounts[account_id]
        movements = sum(
            (e.amount for e in self._entries if e.account_id == account_id and e.value_date <= day),
            ZERO,
        )
        return account.opening_balance + movements

    def ledger_balance(self, account_id: str) -> Decimal:
        return self.closing_balance(account_id, self.business_day)

    def active_holds(self, account_id: str) -> Decimal:
        return sum(
            (a.hold_amount for a in self._authorizations.values()
             if a.account_id == account_id and a.status is AuthStatus.ACTIVE),
            ZERO,
        )

    def available_balance(self, account_id: str) -> Decimal:
        return self.ledger_balance(account_id) - self.active_holds(account_id)

    def fees(self, account_id: str) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries(account_id) if e.entry_type is EntryType.OVERDRAFT_FEE)

    def daily_accrual(self, account_id: str, day: int) -> Decimal:
        return sum((a.amount for a in self._accruals if a.account_id == account_id and a.for_day == day), ZERO)

    # ----------------------------------------------------------------- writes

    def submit(self, event: Event) -> EventRecord:
        problem = self._validate(event)
        if problem:
            return self._record(event, applied=False, message=problem)
        handlers = {
            EventType.CREDIT: self._post_transfer,
            EventType.DEBIT: self._post_transfer,
            EventType.AUTHORIZATION: self._authorize,
            EventType.SETTLEMENT: self._settle,
            EventType.REVERSAL: self._reverse,
        }
        return handlers[event.event_type](event)

    def close_day(self) -> DayClose:
        """End-of-day processing for the current business day, then advance.

        Order: detect restated past days, assess overdraft fees (ascending day
        order, so a fee on day N counts towards day N+1), accrue interest on the
        resulting balances, and on the last day capitalize the accruals.
        """
        if self.window_closed:
            raise RuntimeError("the window is closed; no further day closes")
        day = self.business_day
        errors: list[str] = []
        restatements = self._find_restatements(day)
        fees = self._assess_overdraft_fees(day, errors)
        accruals = self._accrue_interest(day)
        capitalizations = self._capitalize_interest() if day == LAST_DAY else ()

        close = DayClose(
            day=day,
            restatements=restatements,
            fees=fees,
            accruals=accruals,
            capitalizations=capitalizations,
            closing_balances=tuple((a, self.closing_balance(a, day)) for a in self._accounts),
            available_balances=tuple((a, self.closing_balance(a, day) - self.active_holds(a))
                                     for a in self._accounts),
            balance_history=tuple((a, d, self.closing_balance(a, d))
                                  for a in self._accounts for d in range(FIRST_DAY, day + 1)),
            authorizations=self.authorizations(),
            errors=tuple(errors),
        )
        self._day_closes.append(close)
        if day == LAST_DAY:
            self.window_closed = True
        else:
            self.business_day += 1
        return close

    # ------------------------------------------------------------- validation

    def _validate(self, event: Event) -> str | None:
        if self.window_closed:
            return "rejected: the window is closed"
        if any(r.event.event_id == event.event_id for r in self._event_log):
            return f"rejected: duplicate event id {event.event_id}"
        if not FIRST_DAY <= event.day <= LAST_DAY:
            return f"rejected: event day {event.day} is outside Day {FIRST_DAY}..{LAST_DAY}"
        if event.day > self.business_day:
            return f"rejected: event is for Day {event.day} but the ledger is still on Day {self.business_day}"
        account = self._accounts.get(event.account_id)
        if account is None:
            return f"rejected: unknown account {event.account_id}"
        if not is_supported(event.currency) or event.currency != account.currency:
            return f"rejected: currency {event.currency} does not match account currency {account.currency}"
        if event.value_date is None or not FIRST_DAY <= event.value_date <= self.business_day:
            return (f"rejected: value date {event.value_date} must be between Day {FIRST_DAY} "
                    f"and the current business day {self.business_day}")
        if event.event_type is not EventType.REVERSAL:
            if event.amount is None or event.amount <= ZERO:
                return "rejected: amount must be positive"
            if not has_currency_precision(event.amount, event.currency):
                return f"rejected: amount {event.amount} has more decimals than {event.currency} allows"
        if event.instalments < 1:
            return "rejected: instalments must be at least 1"
        if event.instalments > 1 and event.event_type not in (EventType.CREDIT, EventType.DEBIT):
            return "rejected: only credits and debits can be posted in instalments"
        if event.event_type in (EventType.AUTHORIZATION, EventType.SETTLEMENT) and not event.auth_id:
            return "rejected: authorization id is required"
        return None

    # --------------------------------------------------------------- handlers

    def _post_transfer(self, event: Event) -> EventRecord:
        is_credit = event.event_type is EventType.CREDIT
        sign = 1 if is_credit else -1
        entry_type = EntryType.CREDIT if is_credit else EntryType.DEBIT
        parts = split_evenly(event.amount, event.instalments, event.currency)
        for part in parts:
            self._post(event.account_id, entry_type, sign * part, event.value_date, event.event_id)
        message = "posted"
        if len(parts) > 1:
            shown = ", ".join(format_amount(p, event.currency) for p in parts)
            message = f"posted as {len(parts)} instalments: {shown}"
        return self._record(event, applied=True, message=self._with_late_note(event, message))

    def _authorize(self, event: Event) -> EventRecord:
        if event.auth_id in self._authorizations:
            return self._record(event, False, f"rejected: authorization {event.auth_id} already exists")
        available_after_hold = self.available_balance(event.account_id) - event.amount
        approved = available_after_hold >= ZERO
        self._authorizations[event.auth_id] = Authorization(
            auth_id=event.auth_id,
            account_id=event.account_id,
            hold_amount=event.amount,
            requested_day=self.business_day,
            status=AuthStatus.ACTIVE if approved else AuthStatus.DECLINED,
            decided_on_available=self.available_balance(event.account_id),
        )
        shown = format_amount(available_after_hold, event.currency)
        message = (f"approved: available after hold {shown}" if approved
                   else f"declined: available after hold would be {shown}")
        return self._record(event, applied=True, message=self._with_late_note(event, message))

    def _settle(self, event: Event) -> EventRecord:
        auth = self._authorizations.get(event.auth_id)
        if auth is None:
            return self._record(event, False,
                                f"rejected: no authorization {event.auth_id} in the ledger; no funds moved")
        if auth.account_id != event.account_id:
            return self._record(event, False,
                                f"rejected: authorization {event.auth_id} belongs to {auth.account_id}")
        if auth.status is not AuthStatus.ACTIVE:
            return self._record(event, False,
                                f"rejected: authorization {event.auth_id} is {auth.status.value}, not ACTIVE")
        if event.amount > auth.hold_amount:
            return self._record(event, False,
                                f"rejected: settlement {event.amount} exceeds the authorized hold {auth.hold_amount}")
        self._post(event.account_id, EntryType.SETTLEMENT, -event.amount, event.value_date, event.event_id)
        released = auth.hold_amount - event.amount
        self._authorizations[auth.auth_id] = replace(
            auth,
            status=AuthStatus.SETTLED,
            settled_amount=event.amount,
            released_amount=released,
            settled_day=self.business_day,
        )
        message = (f"settled {format_amount(event.amount, event.currency)} against {auth.auth_id}, "
                   f"hold released (unused {format_amount(released, event.currency)})")
        return self._record(event, applied=True, message=self._with_late_note(event, message))

    def _reverse(self, event: Event) -> EventRecord:
        target = next((r for r in self._event_log
                       if r.event.event_id == event.reverses and r.applied), None)
        if target is None:
            return self._record(event, False, f"rejected: no applied event {event.reverses} to reverse")
        if target.event.event_type not in (EventType.CREDIT, EventType.DEBIT):
            return self._record(event, False,
                                f"rejected: only credits and debits can be reversed, not {target.event.event_type.value}")
        if target.event.account_id != event.account_id:
            return self._record(event, False, f"rejected: {event.reverses} belongs to another account")
        already = any(r.applied and r.event.event_type is EventType.REVERSAL and r.event.reverses == event.reverses
                      for r in self._event_log)
        if already:
            return self._record(event, False, f"rejected: {event.reverses} has already been reversed")
        original_entries = [e for e in self._entries if e.source_event_id == event.reverses]
        for original in original_entries:
            self._post(event.account_id, EntryType.REVERSAL, -original.amount, event.value_date, event.event_id)
        total = -sum((e.amount for e in original_entries), ZERO)
        message = f"reversed {event.reverses}: {format_amount(total, event.currency)} value-dated Day {event.value_date}"
        return self._record(event, applied=True, message=self._with_late_note(event, message))

    # -------------------------------------------------------------- day close

    def _find_restatements(self, day: int) -> tuple[Restatement, ...]:
        """Past days whose closing balance moved since the previous close."""
        if not self._day_closes:
            return ()
        previous = {(a, d): balance for a, d, balance in self._day_closes[-1].balance_history}
        found = []
        for (account_id, past_day), before in previous.items():
            now = self.closing_balance(account_id, past_day)
            if now != before:
                found.append(Restatement(account_id, past_day, before, now))
        return tuple(found)

    def _assess_overdraft_fees(self, day: int, errors: list[str]) -> tuple[Entry, ...]:
        """One fee per account per value day whose closing balance is negative.

        Walks every day up to today, oldest first, because a back-valued entry
        can make an earlier day negative and that day's fee then counts in the
        following days' balances. A day that already carries a fee is skipped:
        fees are assessed at most once per day and are never re-assessed.
        """
        assessed = []
        for account in self._accounts.values():
            fee_amount = OVERDRAFT_FEE.get(account.currency)
            for past_day in range(FIRST_DAY, day + 1):
                if self._has_fee(account.account_id, past_day):
                    continue
                balance = self.closing_balance(account.account_id, past_day)
                if balance >= ZERO:
                    continue
                if fee_amount is None:
                    errors.append(f"{account.account_id} Day {past_day} closing balance "
                                  f"{format_amount(balance, account.currency)} is negative but no overdraft "
                                  f"fee is defined for {account.currency}; not charged")
                    continue
                assessed.append(self._post(account.account_id, EntryType.OVERDRAFT_FEE,
                                           -fee_amount, past_day, None))
        return tuple(assessed)

    def _has_fee(self, account_id: str, day: int) -> bool:
        return any(e.account_id == account_id and e.entry_type is EntryType.OVERDRAFT_FEE and e.value_date == day
                   for e in self._entries)

    def _accrue_interest(self, day: int) -> tuple[Accrual, ...]:
        """Bring every day's rounded accrual in line with its value-dated balance.

        The accrual for a day is round(balance x rate) when the balance is
        positive, else zero. If a back-valued entry changed an earlier day's
        balance, the difference is booked as a new adjustment record for that
        day; earlier records are never edited.
        """
        posted = []
        for account in self._accounts.values():
            for past_day in range(FIRST_DAY, day + 1):
                balance = self.closing_balance(account.account_id, past_day)
                target = round_to_currency(max(balance, ZERO) * DAILY_INTEREST_RATE, account.currency)
                difference = target - self.daily_accrual(account.account_id, past_day)
                if difference != ZERO:
                    accrual = Accrual(account.account_id, past_day, difference, day)
                    self._accruals.append(accrual)
                    posted.append(accrual)
        return tuple(posted)

    def _capitalize_interest(self) -> tuple[Entry, ...]:
        """Credit the sum of all rounded accrual records as one entry per account.

        The capitalized amount *is* the sum of the rounded daily accruals, so
        there can be no remainder to discard or carry.
        """
        posted = []
        for account in self._accounts.values():
            total = sum((a.amount for a in self.accruals(account.account_id)), ZERO)
            per_day = sum((self.daily_accrual(account.account_id, d) for d in range(FIRST_DAY, LAST_DAY + 1)), ZERO)
            if total != per_day:  # cannot happen by construction; fail loudly if it ever does
                raise AssertionError(f"{account.account_id}: accruals {total} != daily sum {per_day}")
            if total != ZERO:
                posted.append(self._post(account.account_id, EntryType.INTEREST, total, LAST_DAY, None))
        return tuple(posted)

    # ---------------------------------------------------------------- helpers

    def _post(self, account_id: str, entry_type: EntryType, amount: Decimal,
              value_date: int, source_event_id: str | None) -> Entry:
        entry = Entry(
            sequence=len(self._entries) + 1,
            account_id=account_id,
            entry_type=entry_type,
            amount=amount,
            value_date=value_date,
            booked_day=self.business_day,
            source_event_id=source_event_id,
        )
        self._entries.append(entry)
        return entry

    def _record(self, event: Event, applied: bool, message: str) -> EventRecord:
        record = EventRecord(event=event, processed_day=self.business_day, applied=applied, message=message)
        self._event_log.append(record)
        return record

    def _with_late_note(self, event: Event, message: str) -> str:
        if event.day < self.business_day:
            return (f"{message} [late: belongs to Day {event.day} but arrived after that day closed; "
                    f"booked on Day {self.business_day}, value date Day {event.value_date} kept]")
        return message


def replay(accounts, events) -> Ledger:
    """Feed events in the given order, closing each business day when the stream
    moves past it, then close any remaining days up to the end of the window."""
    ledger = Ledger(accounts)
    for event in events:
        while ledger.business_day < min(event.day, LAST_DAY):
            ledger.close_day()
        ledger.submit(event)
    while not ledger.window_closed:
        ledger.close_day()
    return ledger
