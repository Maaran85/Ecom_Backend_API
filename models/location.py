from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base

class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    iso_code = Column(String(3), nullable=True, unique=True)
    phone_code = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    states = relationship("State", back_populates="country", cascade="all, delete-orphan")

class State(Base):
    __tablename__ = "states"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    country = relationship("Country", back_populates="states")

class PincodeMaster(Base):
    __tablename__ = "pincode_master"

    id = Column(Integer, primary_key=True, index=True)
    circle_name = Column(String, nullable=True)
    region_name = Column(String, nullable=True)
    division_name = Column(String, nullable=True)
    office_name = Column(String, nullable=True)
    pincode = Column(String, index=True, nullable=False)
    office_type = Column(String, nullable=True)
    delivery_status = Column(String, nullable=True)
    district = Column(String, nullable=True)
    state_name = Column(String, nullable=True)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ServiceablePincode(Base):
    __tablename__ = "serviceable_pincodes"

    id = Column(Integer, primary_key=True, index=True)
    pincode = Column(String, index=True, nullable=False)
    dealer_id = Column(Integer, ForeignKey("dealers.id", ondelete="CASCADE"), nullable=True) # If null, applies to global/platform logistics
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
