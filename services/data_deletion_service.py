from sqlalchemy.orm import Session
from sqlalchemy import update
from models.customer_user import CustomerUser
from models.address import Address
from models.user import User
import uuid
from datetime import datetime, timezone

def process_right_to_erasure(db: Session, customer_id: int = None, user_id: int = None):
    """
    Implements GDPR/DPDP Right to be Forgotten by irreversibly anonymizing PII.
    We retain the record IDs to preserve transactional integrity for past orders,
    but scramble all personal identifiers.
    """
    
    if customer_id:
        # 1. Anonymize Customer
        customer = db.query(CustomerUser).filter(CustomerUser.id == customer_id).first()
        if customer:
            random_str = str(uuid.uuid4())[:8]
            db.execute(
                update(CustomerUser).
                where(CustomerUser.id == customer_id).
                values(
                    full_name="Deleted User",
                    email=f"deleted_{random_str}@anonymized.local",
                    phone=f"DEL_{random_str}",
                    dob=None,
                    is_active=False,
                    deleted_at=datetime.now(timezone.utc)
                )
            )
            
            # 2. Anonymize Addresses
            db.execute(
                update(Address).
                where(Address.customer_id == customer_id).
                values(
                    full_name="Deleted User",
                    phone="0000000000",
                    address_line1="Data Erased",
                    address_line2=None,
                    latitude=None,
                    longitude=None
                )
            )

    if user_id:
        # Anonymize Internal User/Staff/Rider
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            random_str = str(uuid.uuid4())[:8]
            db.execute(
                update(User).
                where(User.id == user_id).
                values(
                    full_name="Deleted User",
                    email=f"deleted_{random_str}@anonymized.local",
                    phone=f"DEL_{random_str}",
                    password_hash="ERASED",
                    dob=None,
                    address="Data Erased",
                    aadhaar_number=None,
                    emergency_contact=None,
                    photo_url=None,
                    aadhaar_image=None,
                    is_active=False,
                    deleted_at=datetime.now(timezone.utc)
                )
            )

    db.commit()
    return True
