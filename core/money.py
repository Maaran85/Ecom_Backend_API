from decimal import Decimal, ROUND_HALF_UP

# Internal precision: 4 decimal places. Only the final net amounts round to paise.
INTERMEDIATE_PLACES = 4
FINAL_PLACES = 2


def money(value) -> Decimal:
    """Coerce to Decimal with 4dp intermediate precision."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def money_4dp(value) -> Decimal:
    return money(value)


def money_2dp(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_float(value) -> float:
    return float(value)
