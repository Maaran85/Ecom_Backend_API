from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id", ondelete="CASCADE"), nullable=False)
    query = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("CustomerUser", backref="search_history")
