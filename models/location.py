from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
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
