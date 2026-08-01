import enum


class SettlementStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class TDSThresholdStrategy(str, enum.Enum):
    """How TDS applies when a dealer crosses the exemption threshold mid-FY."""
    PROSPECTIVE = "prospective"      # TDS applies only on the excess above the threshold
    RETROSPECTIVE = "retrospective"  # TDS reapplies to the whole FY once crossed


class OrganizationType(str, enum.Enum):
    INDIVIDUAL = "individual"
    HUF = "huf"
    SOLE_PROPRIETORSHIP = "sole_proprietorship"
    PARTNERSHIP = "partnership"
    LLP = "llp"
    COMPANY = "company"
    PRIVATE_LIMITED = "private_limited"
    PUBLIC_LIMITED = "public_limited"
    OTHER = "other"


class AdjustmentType(str, enum.Enum):
    CREDIT = "credit"  # Amount owed to dealer (e.g. return after settlement)
    DEBIT = "debit"    # Amount owed by dealer (e.g. correction in favour of platform)


class FeeType(str, enum.Enum):
    PERCENTAGE = "percentage"   # % of gross sale
    FLAT = "flat"               # fixed amount per order item
    FIXED_PER_ITEM = "fixed_per_item"
