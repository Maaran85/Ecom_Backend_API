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
    user_id = None
    dealer_id = None
    if user:
        from sqlalchemy import inspect
        try:
            ins = inspect(user)
            if ins.identity:
                user_id = ins.identity[0]
            if "dealer_id" in ins.dict:
                dealer_id = ins.dict["dealer_id"]
        except Exception:
            user_id = getattr(user, "id", None)
            dealer_id = getattr(user, "dealer_id", None)

    audit = AuditLog(
        user_id=user_id,
        dealer_id=dealer_id,
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
