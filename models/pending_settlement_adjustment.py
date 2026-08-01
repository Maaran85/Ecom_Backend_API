import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, DateTime, Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
from core.enums import AdjustmentType


class PendingSettlementAdjustment(Base):
    """
    Credit/debit adjustment queued to be absorbed by the dealer's NEXT settlement.

    Created when a return/refund is approved AFTER a settlement was already PAID.
    Keeps paid settlements immutable (decision: credit in next settlement).
    """
    __tablename__ = "pending_settlement_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False, index=True)

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True)
    source_settlement_id = Column(Integer, ForeignKey("settlements.id", ondelete="SET NULL"), nullable=True)  # originally paid settlement

    type = Column(SQLEnum(AdjustmentType), nullable=False)  # credit / debit
    reason = Column(String, nullable=False)                  # return, refund, cancellation, correction
    amount = Column(Float, nullable=False)
    reference = Column(String, nullable=True)                # e.g. order return id / refund reference

    applied_to_settlement_id = Column(Integer, ForeignKey("settlements.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    dealer = relationship("Dealer", backref="pending_adjustments")
    source_settlement = relationship("Settlement", foreign_keys=[source_settlement_id])
    applied_to_settlement = relationship("Settlement", foreign_keys=[applied_to_settlement_id])
    order = relationship("Order")
    order_item = relationship("OrderItem")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<PendingSettlementAdjustment {self.type.value} {self.amount} reason={self.reason}>"
