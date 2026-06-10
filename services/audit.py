from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from models.audit import AuditLog
from models.user import User

async def log_audit(
    db: AsyncSession,
    user: User,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    description: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """
    Utility to create an audit log entry.
    """
    audit = AuditLog(
        user_id=user.id if user else None,
        dealer_id=user.dealer_id if user and hasattr(user, 'dealer_id') else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        old_values=old_values,
        new_values=new_values,
        description=description,
        ip_address=ip_address
    )
    db.add(audit)
    # We usually flush instead of commit to keep it part of the caller's transaction
    await db.flush()
