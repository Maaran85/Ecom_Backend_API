from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Any, Dict
from decimal import Decimal

def resolve_item_return_policy(item: Any, product: Optional[Any] = None, global_config: Optional[Any] = None) -> Dict[str, Any]:
    """
    Resolves the return/exchange policy tuple (is_returnable, is_exchangeable, return_window_days)
    using the strict 3-tier fallback hierarchy:
      1. OrderItem snapshot fields (if present and not None)
      2. Product policy fields (if product object provided)
      3. Global SettlementConfiguration (15 days fallback, is_returnable=True, is_exchangeable=True)
    """
    # 1. OrderItem Snapshot
    is_ret = getattr(item, 'is_returnable', None)
    is_exc = getattr(item, 'is_exchangeable', None)
    ret_win = getattr(item, 'return_window_days', None)

    # 2. Product Policy Fallback
    if is_ret is None and product is not None:
        is_ret = getattr(product, 'is_returnable', None)
    if is_exc is None and product is not None:
        is_exc = getattr(product, 'is_exchangeable', None)
    if ret_win is None and product is not None:
        ret_win = getattr(product, 'return_window_days', None)

    # 3. Global Fallback
    if is_ret is None:
        is_ret = True
    if is_exc is None:
        is_exc = True
    if ret_win is None or ret_win is None:
        if global_config is not None and getattr(global_config, 'return_window_days', None) is not None:
            ret_win = int(global_config.return_window_days)
        else:
            ret_win = 15

    return {
        "is_returnable": bool(is_ret),
        "is_exchangeable": bool(is_exc),
        "return_window_days": int(ret_win)
    }


def get_effective_protection_window(item: Any, product: Optional[Any] = None, global_config: Optional[Any] = None) -> int:
    """
    Calculates the effective customer protection window (in days) required before dealer settlement.
    
    Rules:
      - Non-returnable & Non-exchangeable (is_returnable=False AND is_exchangeable=False) -> 0 days protection window.
      - Otherwise -> return_window_days (effective customer return/exchange window).
    """
    policy = resolve_item_return_policy(item, product=product, global_config=global_config)
    
    if not policy["is_returnable"] and not policy["is_exchangeable"]:
        return 0
        
    return policy["return_window_days"]


def validate_customer_request(
    item: Any,
    delivered_at: datetime,
    is_exchange: bool = False,
    now: Optional[datetime] = None,
    product: Optional[Any] = None,
    global_config: Optional[Any] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates whether a customer return or exchange request is eligible under the item's policy.
    """
    policy = resolve_item_return_policy(item, product=product, global_config=global_config)
    curr_now = now or datetime.now(timezone.utc)

    if not is_exchange and not policy["is_returnable"]:
        return False, "This product is non-returnable"

    if is_exchange and not policy["is_exchangeable"]:
        return False, "This product is non-exchangeable"

    days_since = (curr_now - delivered_at).days
    window_days = policy["return_window_days"]

    if days_since > window_days:
        action_name = "Exchange" if is_exchange else "Return"
        return False, f"{action_name} window ({window_days} days) has expired"

    return True, None


def is_item_settlement_matured(
    item: Any,
    delivered_at: datetime,
    as_of: Optional[datetime] = None,
    product: Optional[Any] = None,
    global_config: Optional[Any] = None,
) -> bool:
    """
    Returns True if delivered_at + effective_protection_window <= as_of.
    """
    curr_as_of = as_of or datetime.now(timezone.utc)
    eff_window = get_effective_protection_window(item, product=product, global_config=global_config)
    maturity_date = delivered_at + timedelta(days=eff_window)
    return curr_as_of >= maturity_date
