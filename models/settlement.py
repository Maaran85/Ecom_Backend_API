import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Date,
    Enum as SQLEnum, JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
from core.enums import SettlementStatus, AdjustmentType


class Settlement(Base):
    """A dealer settlement covering a batch of matured orders (one per run)."""
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, index=True)
    settlement_number = Column(String, unique=True, index=True, nullable=True)  # STL-2026-0001

    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(SQLEnum(SettlementStatus), default=SettlementStatus.DRAFT, nullable=False, index=True)

    # Financial year attribution (official = settlement date)
    financial_year = Column(String, nullable=False, index=True)  # "2026-2027"
    fy_start_date = Column(Date, nullable=False)
    fy_end_date = Column(Date, nullable=False)

    # Period covered by this settlement
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    settlement_date = Column(Date, nullable=True, index=True)
    mature_date = Column(Date, nullable=True, index=True)

    # --- Totals (rounded to paise) ---
    gross_sale_amount = Column(Float, default=0.0, nullable=False)
    total_marketplace_fee = Column(Float, default=0.0, nullable=False)
    total_marketing_fee = Column(Float, default=0.0, nullable=False)
    total_shipping_received = Column(Float, default=0.0, nullable=False)  # customer shipping (self-logistics)
    total_logistics_charge = Column(Float, default=0.0, nullable=False)   # partner logistics deduction
    total_gst_on_fees = Column(Float, default=0.0, nullable=False)        # GST component the platform keeps on fees
    total_adjustments = Column(Float, default=0.0, nullable=False)        # net credit/debit adjustments in this settlement

    gross_tds_base = Column(Float, default=0.0, nullable=False)           # cumulative base considered for TDS
    tds_exempt_portion = Column(Float, default=0.0, nullable=False)       # shielded by exemption limit
    total_tds = Column(Float, default=0.0, nullable=False)
    tds_rate_applied = Column(Float, default=0.0, nullable=False)

    net_payable = Column(Float, default=0.0, nullable=False)

    # --- Precision / audit snapshots ---
    precise_values = Column(JSON, nullable=True)     # 4dp calculation detail
    settlement_version = Column(String, nullable=False, default="1.0")  # engine version that produced this
    config_snapshot = Column(JSON, nullable=True)    # {tds: {...}, fees: {...}} config at time of generation
    rule_snapshot = Column(JSON, nullable=True)      # dealer org type, PAN presence, threshold strategy, rates
    calculation_snapshot = Column(JSON, nullable=True)  # per-line breakdown

    # --- Workflow timestamps / actors ---
    generated_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    paid_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancel_reason = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    # Payment link (created only after APPROVED)
    remittance_id = Column(Integer, ForeignKey("dealer_remittances.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    dealer = relationship("Dealer", backref="settlements")
    items = relationship("SettlementItem", back_populates="settlement", cascade="all, delete-orphan")
    adjustments = relationship(
        "SettlementAdjustment",
        back_populates="settlement",
        cascade="all, delete-orphan",
        foreign_keys="SettlementAdjustment.settlement_id",
    )
    approver = relationship("User", foreign_keys=[approved_by])
    payer = relationship("User", foreign_keys=[paid_by])
    canceller = relationship("User", foreign_keys=[cancelled_by])
    remittance = relationship("DealerRemittance")

    def __repr__(self) -> str:
        return f"<Settlement {self.settlement_number} dealer={self.dealer_id} {self.status.value}>"


class SettlementItem(Base):
    """One order-item line inside a settlement (financial snapshot, immutable)."""
    __tablename__ = "settlement_items"

    id = Column(Integer, primary_key=True, index=True)
    settlement_id = Column(Integer, ForeignKey("settlements.id", ondelete="CASCADE"), nullable=False, index=True)

    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)

    # Audit dates
    order_number = Column(String, nullable=True)
    order_date = Column(Date, nullable=True)         # actual order placement date
    settlement_date = Column(Date, nullable=False)    # FY attribution date (official axis)
    mature_date = Column(Date, nullable=True)        # order return maturity date

    # Item financials (precise)
    item_price = Column(Float, nullable=False)        # unit price at checkout (GST-inclusive)
    quantity = Column(Integer, nullable=False)
    gross_sale_amount = Column(Float, nullable=False)  # item_price * qty

    marketplace_fee = Column(Float, default=0.0, nullable=False)   # inclusive of GST (platform keeps)
    marketing_fee = Column(Float, default=0.0, nullable=False)     # inclusive of GST (platform keeps)
    shipping_received = Column(Float, default=0.0, nullable=False) # customer shipping to dealer (self-logistics)
    logistics_charge = Column(Float, default=0.0, nullable=False)  # partner logistics deduction (incl. GST)

    tds_base = Column(Float, default=0.0, nullable=False)          # portion of gross subject to TDS this line
    tds_rate = Column(Float, default=0.0, nullable=False)
    tds_amount = Column(Float, default=0.0, nullable=False)
    tds_exempt_portion = Column(Float, default=0.0, nullable=False)  # shielded by threshold this line

    net_payable = Column(Float, default=0.0, nullable=False)
    precise_values = Column(JSON, nullable=True)  # 4dp line detail

    delivery_type = Column(String, nullable=True)  # own_rider, courier, logistics (snapshot)

    is_cancelled = Column(Boolean, default=False, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    settlement = relationship("Settlement", back_populates="items")
    order_item = relationship("OrderItem")
    order = relationship("Order")

    @property
    def delivery_date(self):
        if self.order_item and self.order_item.delivered_at:
            if hasattr(self.order_item.delivered_at, 'date'):
                return self.order_item.delivered_at.date()
            return self.order_item.delivered_at
        if self.order and hasattr(self.order, 'delivered_at') and self.order.delivered_at:
            if hasattr(self.order.delivered_at, 'date'):
                return self.order.delivered_at.date()
            return self.order.delivered_at
        return self.order_date

    @property
    def product_id(self):
        if self.order_item and self.order_item.product_id:
            return str(self.order_item.product_id)
        return str(self.order_item_id) if self.order_item_id else None

    @property
    def product_name(self):
        if self.order_item and self.order_item.product:
            return getattr(self.order_item.product, 'name', None) or getattr(self.order_item.product, 'title', None)
        return "Product Item"

    def __repr__(self) -> str:
        return f"<SettlementItem settlement={self.settlement_id} order_item={self.order_item_id} net={self.net_payable}>"


class SettlementAdjustment(Base):
    """
    Credit/debit adjustment referencing a previously settled & paid order.

    Used when a return/refund is approved AFTER a settlement was PAID.
    Immutable settlements are never reopened; the impact flows through
    the dealer's NEXT settlement as an adjustment entry.
    """
    __tablename__ = "settlement_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    settlement_id = Column(Integer, ForeignKey("settlements.id", ondelete="CASCADE"), nullable=False, index=True)

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True)
    source_settlement_id = Column(Integer, ForeignKey("settlements.id", ondelete="SET NULL"), nullable=True)  # originally paid settlement

    type = Column(SQLEnum(AdjustmentType), nullable=False)  # credit / debit
    reason = Column(String, nullable=False)                  # return, refund, cancellation, correction
    amount = Column(Float, nullable=False)
    reference = Column(String, nullable=True)                # e.g. order return id / refund reference

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    settlement = relationship("Settlement", back_populates="adjustments", foreign_keys=[settlement_id])
    source_settlement = relationship("Settlement", foreign_keys=[source_settlement_id])
    order = relationship("Order")
    order_item = relationship("OrderItem")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<SettlementAdjustment {self.type.value} {self.amount} reason={self.reason}>"
