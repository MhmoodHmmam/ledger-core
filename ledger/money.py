"""Currency precision, rounding and exact splitting.

Every amount in the ledger is a ``Decimal`` held at its currency's own precision.
Floats are never used: 0.1 + 0.2 != 0.3 in binary floating point, and a ledger
must add up to the last fils.
"""

from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 minor units. AED has 100 fils to the dirham, BHD has 1,000 fils to the dinar.
MINOR_UNITS = {"AED": 2, "BHD": 3}

# Commercial rounding: 0.005 AED becomes 0.01. Chosen over banker's rounding
# (ROUND_HALF_EVEN) because it is what a customer checking by hand expects.
# No amount in the given stream lands exactly on a half, so this choice does
# not change any printed number; tests pin the behaviour anyway.
ROUNDING = ROUND_HALF_UP


def is_supported(currency: str) -> bool:
    return currency in MINOR_UNITS


def quantum(currency: str) -> Decimal:
    """Smallest representable amount: Decimal('0.01') for AED, Decimal('0.001') for BHD."""
    return Decimal(1).scaleb(-MINOR_UNITS[currency])


def round_to_currency(amount: Decimal, currency: str) -> Decimal:
    return amount.quantize(quantum(currency), rounding=ROUNDING)


def has_currency_precision(amount: Decimal, currency: str) -> bool:
    """True when the amount needs no rounding, e.g. AED 1.50 yes, AED 1.505 no."""
    return amount == round_to_currency(amount, currency)


def split_evenly(amount: Decimal, parts: int, currency: str) -> list[Decimal]:
    """Split a positive amount into ``parts`` instalments that sum exactly to it.

    Works in whole minor units. Leftover minor units go to the earliest
    instalments, one each, so BHD 10.000 / 3 becomes 3.334, 3.333, 3.333.
    """
    if parts < 1:
        raise ValueError("parts must be at least 1")
    unit = quantum(currency)
    total_minor_units = int(amount / unit)
    base, leftover = divmod(total_minor_units, parts)
    return [(base + (1 if index < leftover else 0)) * unit for index in range(parts)]


def format_amount(amount: Decimal, currency: str) -> str:
    """'1,200.00' for AED, '10.000' for BHD. Signed: '-370.00'."""
    return f"{amount:,.{MINOR_UNITS[currency]}f}"
