import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
from core.config import settings
from sqlalchemy_utils import EncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

class DeliveryRider(Base):
    __tablename__ = "delivery_riders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    business_name = Column(String, nullable=True) # If they work independently or for a agency
    
    # Association (Managed by Admin or Dealer)
    managed_by = Column(String, default="admin") # "admin" or "dealer"
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=True) # If managed by a specific dealer
    partner_id = Column(Integer, ForeignKey("logistics_partners.id", ondelete="SET NULL"), nullable=True) # If they work for a specific partner

    # Rider Specific Details
    vehicle_type = Column(String, nullable=True) # Bike, Scooter, Cycle, Van
    vehicle_number = Column(String, nullable=True)
    vehicle_model = Column(String, nullable=True)
    insurance_expiry = Column(String, nullable=True) # ISO format date string
    dob = Column(String, nullable=True)
    
    phone_number = Column("phone_number", String, nullable=True)
    license_number = Column(EncryptedType(String, settings.ENCRYPTION_KEY, AesEngine, 'pkcs5'), nullable=True)
    aadhaar_number = Column(EncryptedType(String, settings.ENCRYPTION_KEY, AesEngine, 'pkcs5'), nullable=True)
    emergency_contact = Column(String, nullable=True)
    address = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    
    # Document Verification Images
    aadhaar_image = Column(String, nullable=True)
    license_image = Column(String, nullable=True)
    
    # Bank Details (For payouts)
    bank_name = Column(String, nullable=True)
    account_number = Column(EncryptedType(String, settings.ENCRYPTION_KEY, AesEngine, 'pkcs5'), nullable=True)
    ifsc_code = Column(EncryptedType(String, settings.ENCRYPTION_KEY, AesEngine, 'pkcs5'), nullable=True)
    upi_id = Column(EncryptedType(String, settings.ENCRYPTION_KEY, AesEngine, 'pkcs5'), nullable=True)
    
    # Hub Mapping
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id", ondelete="SET NULL"), nullable=True)
    # Availability
    is_available = Column(Boolean, default=True)
    current_status = Column(String, default="active") # active, busy, offline
    service_zones = Column(String, nullable=True) # Comma-separated pincodes or city names
    
    # Location (For real-time tracking later)
    current_lat = Column(Float, nullable=True)
    current_long = Column(Float, nullable=True)
    
    # Meta
    is_approved = Column(Boolean, default=False)
    average_rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    current_balance = Column(Float, default=0.0)
    total_earnings = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    @property
    def full_name(self):
        return self.user.full_name if self.user and self.user.full_name else None
        
    @property
    def user_email(self):
        return self.user.email if self.user else None

    # Relationships
    user = relationship("User", backref="rider_profile", foreign_keys=[user_id])
    dealer = relationship("Dealer", backref="riders")
    partner = relationship("LogisticsPartner", back_populates="riders")
    hub = relationship("DeliveryHub")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
