from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class Dealer(Base):
    __tablename__ = "dealers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    business_name = Column(String, nullable=False)
    business_address = Column(String, nullable=True)
    gst_number = Column(String, nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)
    
    # Statuses
    profile_status = Column(String, default="pending", nullable=False) # pending, completed
    access_status = Column(String, default="pending", nullable=False)  # pending, active, reject
    is_active = Column(Boolean, default=True, nullable=False)
    reject_reason = Column(String, nullable=True)
    
    # Company Details Extension
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    pincode = Column(String, nullable=True)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=True)
    state_id = Column(Integer, ForeignKey('states.id'), nullable=True)
    lat_long = Column(String, nullable=True)
    
    business_phone = Column(String, nullable=True)
    
    # Documents
    company_photo_url = Column(String, nullable=True)
    gst_certificate_url = Column(String, nullable=True)
    incorporation_certificate_url = Column(String, nullable=True)
    pan_number = Column(String, nullable=True)
    pan_photo_url = Column(String, nullable=True)
    aadhaar_number = Column(String, nullable=True)
    aadhaar_photo_url = Column(String, nullable=True)
    cin_number = Column(String, nullable=True)
    cin_certificate_url = Column(String, nullable=True)
    company_logo_url = Column(String, nullable=True)
    
    # Bank Details
    bank_name = Column(String, nullable=True)
    bank_address = Column(String, nullable=True)
    bank_branch = Column(String, nullable=True)
    ifsc_code = Column(String, nullable=True)
    account_holder_name = Column(String, nullable=True)
    account_number = Column(String, nullable=True)

    # Delivery Settings
    delivery_charge = Column(Float, default=0.0, nullable=False)        # flat fee per order from this dealer
    free_delivery_above = Column(Float, default=0.0, nullable=False)    # 0 = always free; >0 = waived above this amount
    estimated_delivery_days = Column(Integer, default=7, nullable=False) # e.g. 5 means 5 days from order date
    
    # Financial Settings
    platform_fee_percent = Column(Float, default=5.0, nullable=False)  # The % the platform takes from each sale
    free_delivery_above = Column(Float, default=0.0, nullable=False)    # 0 = always free; >0 = waived above this amount
    estimated_delivery_days = Column(Integer, default=7, nullable=False) # e.g. 5 means 5 days from order date

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", backref="dealer_profile", foreign_keys=[user_id])
    products = relationship("Product", back_populates="dealer")
    country = relationship("Country", foreign_keys=[country_id])
    state_rel = relationship("State", foreign_keys=[state_id])
    logistics_partners = relationship("LogisticsPartner", secondary="dealer_logistics_mapping", back_populates="dealers")
