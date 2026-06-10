from sqlalchemy import Column, Integer, String, DateTime, Boolean, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class CustomerUser(Base):
    __tablename__ = "customer_users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    otp_code = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def role(self):
        from models.user import UserRole
        return UserRole.CUSTOMER

    @property
    def is_customer(self) -> bool:
        return True

    # Relationships (to be added as we refactor other models)
    # addresses = relationship("Address", back_populates="customer")
    # orders = relationship("Order", back_populates="customer")
    # cart_items = relationship("CartItem", back_populates="customer")
    # wishlist_items = relationship("WishlistItem", back_populates="customer")
