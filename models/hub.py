import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class DeliveryHub(Base):
    __tablename__ = "delivery_hubs"

    id = Column(Integer, primary_key=True, index=True)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)

    # Hub Info
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)  # Legacy string state
    state_id = Column(Integer, ForeignKey("states.id"), nullable=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True)
    pincode = Column(String, nullable=True)
    lat_long = Column(String, nullable=True)
    max_delivery_radius = Column(Float, nullable=True)  # Max radius in km for local delivery

    # Contact
    contact_person = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # Meta
    is_active = Column(Boolean, default=True, nullable=False)
    is_showroom = Column(Boolean, default=False, nullable=False)
    notes = Column(String, nullable=True)
    hub_type = Column(String, nullable=True)
    capacity = Column(String, nullable=True)
    operating_hours = Column(String, nullable=True)
    emergency_phone = Column(String, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    dealer = relationship("Dealer", backref="hubs")
    user = relationship("User", backref="hub_profile", foreign_keys=[user_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
