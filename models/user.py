import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
from core.config import settings
from sqlalchemy_utils import EncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
import enum

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    ADMIN_USER = "admin_user"
    DEALER = "dealer"
    DEALER_MANAGER = "dealer_manager"
    DEALER_INVENTORY = "dealer_inventory"
    DEALER_ORDERS = "dealer_orders"
    DEALER_FINANCE = "dealer_finance"
    DELIVERY_PARTNER = "delivery_partner"
    CUSTOMER = "customer"
    HUB = "hub"
    HUB_MANAGER = "hub_manager"
    HUB_STAFF = "hub_staff"
    HUB_DISPATCHER = "hub_dispatcher"
    HUB_RETURNS = "hub_returns"
    RIDER = "rider"
    LOGISTICS_ADMIN = "logistics_admin"
    LOGISTICS_MANAGER = "logistics_manager"
    SHOWROOM_MANAGER = "showroom_manager"
    SHOWROOM_STAFF = "showroom_staff"
    PARTNER_HELPDESK_OPERATOR = "partner_helpdesk_operator"
    PARTNER_HELPDESK_SUPERVISOR = "partner_helpdesk_supervisor"
    PARTNER_HELPDESK_MANAGER = "partner_helpdesk_manager"
    PARTNER_BACKOFFICE = "partner_backoffice"
    PARTNER_LOGISTICS_SPECIALIST = "partner_logistics_specialist"
    PARTNER_FINANCE_SPECIALIST = "partner_finance_specialist"
    PARTNER_CATALOG_MANAGER = "partner_catalog_manager"
    PARTNER_TECH_SUPPORT = "partner_tech_support"
    PARTNER_SUPPORT_MANAGER = "partner_support_manager"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    # phone_number = Column(String, nullable=True) # Consolidated into 'phone'
    role = Column(SQLEnum(UserRole), default=UserRole.CUSTOMER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    employee_id = Column(String, unique=True, nullable=True)
    shift_type = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    address = Column(String, nullable=True)
    aadhaar_number = Column(EncryptedType(String, settings.ENCRYPTION_KEY, AesEngine, 'pkcs5'), nullable=True)
    emergency_contact = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    aadhaar_image = Column(String, nullable=True)
    otp_code = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Association with a dealer (for dealer staff and hub managers)
    from sqlalchemy import ForeignKey
    dealer_id = Column(UUID(as_uuid=True), ForeignKey('dealers.id'), nullable=True)
    hub_id = Column(Integer, ForeignKey('delivery_hubs.id'), nullable=True)
    logistics_partner_id = Column(Integer, ForeignKey('logistics_partners.id'), nullable=True)
    partner_id = Column(Integer, ForeignKey('partners.id'), nullable=True)
    
    # Hierarchy for Helpdesk / Staff
    supervisor_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Relationships
    # (Avoid circular import if needed by using string reference)
    dealer = relationship("Dealer", foreign_keys=[dealer_id])
    hub = relationship("DeliveryHub", backref="users", foreign_keys=[hub_id])
    logistics_partner = relationship("LogisticsPartner", backref="users", foreign_keys=[logistics_partner_id])
    partner = relationship("Partner", backref="users", foreign_keys=[partner_id])
    supervisor = relationship("User", remote_side=[id], foreign_keys=[supervisor_id], backref="subordinates")
    @property
    def is_customer(self) -> bool:
        return False
