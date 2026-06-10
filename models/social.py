from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class DealerFollow(Base):
    __tablename__ = "dealer_follows"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id", ondelete="CASCADE"), nullable=False)
    dealer_id = Column(Integer, ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    customer = relationship("CustomerUser", backref="followed_dealers")
    dealer = relationship("Dealer", backref="followers")
