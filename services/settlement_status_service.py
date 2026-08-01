from typing import Set

from core.enums import SettlementStatus


class InvalidTransitionError(Exception):
    """Raised when a settlement status change violates the state machine."""


ALLOWED_TRANSITIONS: dict[SettlementStatus, Set[SettlementStatus]] = {
    SettlementStatus.DRAFT: {SettlementStatus.GENERATED, SettlementStatus.CANCELLED},
    SettlementStatus.GENERATED: {SettlementStatus.APPROVED, SettlementStatus.CANCELLED},
    SettlementStatus.APPROVED: {SettlementStatus.PAID},
    SettlementStatus.PAID: set(),        # terminal
    SettlementStatus.CANCELLED: set(),   # terminal
}


def assert_transition(current: SettlementStatus, target: SettlementStatus) -> None:
    if current == target:
        raise InvalidTransitionError(f"Settlement is already {current.value}")
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition settlement from '{current.value}' to '{target.value}'"
        )


def can_transition(current: SettlementStatus, target: SettlementStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
