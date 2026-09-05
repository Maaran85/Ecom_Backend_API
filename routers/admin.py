"""
Admin dashboard and management router
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, case
from sqlalchemy.orm import selectinload
from core.database import get_db
from core.permissions import require_admin, require_super_admin
from models import User, Dealer, Product, Category, Order, OrderItem, UserRole, DeliveryRider, DeliveryHub, LogisticsPartner, LogisticsRemittance, Payment, PaymentMethod, PaymentStatus, DealerRemittance, RechargeTransaction, RechargeStatus
from schemas.rider import Rider as RiderSchema, RiderUpdate
from schemas.user import AdminUserCreate, AdminUserUpdate
from schemas.logistics import RemittanceResponse, RemittanceStatusUpdate
from core.security import get_password_hash

router = APIRouter()

class DealerAdminCreate(BaseModel):
    email: str
    password: str
    full_name: str
    business_phone: Optional[str] = None
    business_name: str
    business_address: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    partner_id: Optional[int] = None
    # Location details
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    lat_long: Optional[str] = None
    # Bank Details
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    # Documents
    company_photo_url: Optional[str] = None
    gst_certificate_url: Optional[str] = None
    incorporation_certificate_url: Optional[str] = None
    pan_photo_url: Optional[str] = None
    aadhaar_photo_url: Optional[str] = None
    cin_number: Optional[str] = None
    cin_certificate_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    signature_image_url: Optional[str] = None
    is_auction_enabled: bool = False

class DealerAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    business_name: Optional[str] = None
    business_address: Optional[str] = None
    gst_number: Optional[str] = None
    organization_type: Optional[str] = None  # individual, huf, company, llp, private_limited, ...
    business_phone: Optional[str] = None
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    lat_long: Optional[str] = None
    country_id: Optional[int] = None
    state_id: Optional[int] = None
    partner_id: Optional[int] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    is_active: Optional[bool] = None
    # Documents
    company_photo_url: Optional[str] = None
    gst_certificate_url: Optional[str] = None
    incorporation_certificate_url: Optional[str] = None
    pan_photo_url: Optional[str] = None
    aadhaar_photo_url: Optional[str] = None
    cin_number: Optional[str] = None
    cin_certificate_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    signature_image_url: Optional[str] = None
    is_auction_enabled: Optional[bool] = None
    platform_fee_amount: Optional[float] = None

@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics (admin only)"""
    # Count users by role
    users_count = await db.execute(select(func.count(User.id)))
    total_users = users_count.scalar()
    # Count dealers
    dealers_count = await db.execute(select(func.count(Dealer.id)))
    total_dealers = dealers_count.scalar()
    # Count approved dealers
    approved_dealers_count = await db.execute(
        select(func.count(Dealer.id)).where(Dealer.is_approved == True)
    )
    approved_dealers = approved_dealers_count.scalar()
    # Count products
    products_count = await db.execute(select(func.count(Product.id)))
    total_products = products_count.scalar()
    # Count approved products
    approved_products_count = await db.execute(
        select(func.count(Product.id)).where(Product.is_approved == True)
    )
    approved_products = approved_products_count.scalar()
    # Count orders
    orders_count = await db.execute(select(func.count(Order.id)))
    total_orders = orders_count.scalar()
    
    # Count categories
    categories_count = await db.execute(select(func.count(Category.id)))
    total_categories = categories_count.scalar()
    
    # Count logistics partners
    partners_count = await db.execute(select(func.count(LogisticsPartner.id)))
    total_partners = partners_count.scalar()
    
    # Pending Remittances (Dealer + Logistics depending on what we want to count, let's just count Dealer Remittances for now)
    dealer_remit_count = await db.execute(select(func.count(DealerRemittance.id)).where(DealerRemittance.status == 'pending'))
    pending_remittances = dealer_remit_count.scalar()
    logistics_remit_count = await db.execute(select(func.count(LogisticsRemittance.id)).where(LogisticsRemittance.status == 'pending'))
    pending_remittances += logistics_remit_count.scalar()

    return {
        "users": {"total": total_users},
        "dealers": {
            "total": total_dealers,
            "approved": approved_dealers,
            "pending": total_dealers - approved_dealers,
        },
        "products": {
            "total": total_products,
            "approved": approved_products,
            "pending": total_products - approved_products,
        },
        "orders": {"total": total_orders},
        "pending_assignments": (
            await db.execute(select(func.count(OrderItem.id)).where(OrderItem.logistics_partner_id == None))
        ).scalar(),
        "categories": total_categories,
        "partners": total_partners,
        "pending_remittances": pending_remittances
    }

@router.get("/pending-approvals")
async def get_pending_approvals(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get pending dealer and product approvals (admin only)"""
    pending_dealers_result = await db.execute(
        select(Dealer).where(Dealer.is_deleted == False)
        .options(
            selectinload(Dealer.user),
            selectinload(Dealer.country),
            selectinload(Dealer.state_rel)
        )
        .where(Dealer.is_approved == False)
    )
    pending_dealers = pending_dealers_result.scalars().all()
    pending_products_result = await db.execute(select(Product).where(Product.is_approved == False))
    pending_products = pending_products_result.scalars().all()
    return {
        "pending_dealers": [
            {
                "id": d.id, "business_name": d.business_name, "business_address": d.business_address,
                "tax_id": d.gst_number, "user_id": d.user_id,
                "user_email": d.user.email if d.user else None,
                "full_name": d.user.full_name if d.user else None,
                "is_approved": d.is_approved, "profile_status": d.profile_status,
                "access_status": d.access_status, "created_at": d.created_at,
                "business_phone": d.business_phone,
                "city": d.city, "state": d.state, "pincode": d.pincode,
                "country_id": d.country_id, "country_name": d.country.name if d.country else None,
                "state_id": d.state_id, "state_name": d.state_rel.name if d.state_rel else None,
                "partner_id": d.partner_id,
                "pan_number": d.pan_number, "bank_name": d.bank_name,
                "account_number": d.account_number, "ifsc_code": d.ifsc_code,
                "reject_reason": d.reject_reason, "is_active": d.is_active,
                "company_photo_url": d.company_photo_url, "gst_certificate_url": d.gst_certificate_url,
                "incorporation_certificate_url": d.incorporation_certificate_url,
                "pan_photo_url": d.pan_photo_url, "aadhaar_number": d.aadhaar_number,
                "aadhaar_photo_url": d.aadhaar_photo_url,
                "cin_number": d.cin_number,
                "cin_certificate_url": d.cin_certificate_url,
                "company_logo_url": d.company_logo_url
            }
            for d in pending_dealers
        ],
        "pending_products": [
            {"id": str(p.id), "name": p.name, "dealer_id": str(p.dealer_id), "price": p.dealer_price, "mrp": p.mrp, "created_at": p.created_at}
            for p in pending_products
        ]
    }

@router.get("/users")
async def list_all_users(
    skip: int = 0,
    limit: int = 200,
    role: str = None,
    dealer_id: UUID = None,
    logistics_partner_id: int = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users with optional role, dealer and logistics partner filter (admin only)"""
    print(f"DEBUG: list_all_users called with role={role}, dealer_id={dealer_id}, logistics_partner_id={logistics_partner_id}")
    from sqlalchemy.orm import selectinload
    query = select(User).options(
        selectinload(User.dealer), 
        selectinload(User.logistics_partner),
        selectinload(User.partner),
        selectinload(User.supervisor)
    ).offset(skip).limit(limit)
    if role and role != 'null':
        r = role.lower()
        if r == 'logistics':
            logistics_roles = [
                UserRole.LOGISTICS_ADMIN, UserRole.LOGISTICS_MANAGER
            ]
            query = query.where(User.role.in_(logistics_roles))
        elif r == 'dealer':
            dealer_roles = [
                UserRole.DEALER
            ]
            query = query.where(User.role.in_(dealer_roles))
        elif r == 'admin':
            admin_roles = [UserRole.ADMIN, UserRole.SUPER_ADMIN]
            query = query.where(User.role.in_(admin_roles))
        elif r == 'helpdesk':
            helpdesk_roles = [
                UserRole.PARTNER_HELPDESK_OPERATOR,
                UserRole.PARTNER_HELPDESK_SUPERVISOR,
                UserRole.PARTNER_HELPDESK_MANAGER
            ]
            query = query.where(User.role.in_(helpdesk_roles))
        elif r == 'backoffice':
            backoffice_roles = [
                UserRole.PARTNER_BACKOFFICE,
                UserRole.PARTNER_LOGISTICS_SPECIALIST,
                UserRole.PARTNER_FINANCE_SPECIALIST,
                UserRole.PARTNER_CATALOG_MANAGER,
                UserRole.PARTNER_TECH_SUPPORT,
                UserRole.PARTNER_SUPPORT_MANAGER
            ]
            query = query.where(User.role.in_(backoffice_roles))
        else:
            query = query.where(User.role == role)
    if dealer_id:
        query = query.where(User.dealer_id == dealer_id)
    if logistics_partner_id:
        query = query.where(User.logistics_partner_id == logistics_partner_id)
    result = await db.execute(query)
    users = result.scalars().all()
    print(f"DEBUG: Returning {len(users)} users. Roles: {[u.role for u in users[:5]]}...")
    return [
        {
            "id": u.id, "email": u.email, "full_name": u.full_name,
            "phone": u.phone,
            "role": u.role, "is_active": u.is_active, "created_at": u.created_at,
            "dealer_id": u.dealer_id, "dealer_name": u.dealer.business_name if u.dealer else None,
            "employee_id": u.employee_id, "dob": u.dob, "address": u.address,
            "aadhaar_number": u.aadhaar_number, "emergency_contact": u.emergency_contact,
            "photo_url": u.photo_url, "aadhaar_image": u.aadhaar_image, "shift_type": u.shift_type,
            "logistics_partner_id": u.logistics_partner_id,
            "logistics_partner_name": u.logistics_partner.name if u.logistics_partner else None,
            "partner_id": u.partner_id,
            "partner_name": u.partner.partner_name if getattr(u, 'partner', None) else None,
            "supervisor_id": u.supervisor_id,
            "supervisor_name": u.supervisor.full_name if u.supervisor else None
        }
        for u in users
    ]

def _manual_decrypt(val: str) -> str:
    if not val or len(val) < 20: return val
    try:
        from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
        from core.config import settings
        engine = AesEngine()
        engine._update_key(settings.ENCRYPTION_KEY)
        decrypted = engine.decrypt(val)
        if isinstance(decrypted, bytes):
            return decrypted.decode('utf-8')
        return str(decrypted) if decrypted else val
    except Exception:
        pass
    
    try:
        import base64
        from cryptography.fernet import Fernet
        from core.config import settings
        key = base64.urlsafe_b64encode(settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b'0'))
        f = Fernet(key)
        return f.decrypt(val.encode()).decode()
    except Exception:
        pass
    return val

@router.get("/dealers")
async def list_all_dealers(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all dealers (admin only)"""
    from sqlalchemy.orm import selectinload
    query = select(Dealer).where(Dealer.is_deleted == False).options(
        selectinload(Dealer.user),
        selectinload(Dealer.country),
        selectinload(Dealer.state_rel)
    ).offset(skip).limit(limit)
    result = await db.execute(query)
    dealers = result.scalars().all()
    return [
        {
            "id": d.id, "business_name": d.business_name, "business_address": d.business_address,
            "tax_id": d.gst_number, "user_id": d.user_id,
            "user_email": d.user.email if d.user else None,
            "full_name": d.user.full_name if d.user else None,
            "is_approved": d.is_approved, "profile_status": d.profile_status,
            "access_status": d.access_status, "created_at": d.created_at,
            "business_phone": d.business_phone,
            "city": d.city, "pincode": d.pincode,
            "country_id": d.country_id, "country_name": d.country.name if d.country else None,
            "state_id": d.state_id, "state_name": d.state_rel.name if d.state_rel else None,
            "partner_id": d.partner_id,
            "pan_number": d.pan_number, "bank_name": d.bank_name,
            "account_number": _manual_decrypt(d.account_number), "ifsc_code": _manual_decrypt(d.ifsc_code),
            "reject_reason": d.reject_reason, "is_active": d.is_active,
            "company_photo_url": d.company_photo_url, "gst_certificate_url": d.gst_certificate_url,
            "incorporation_certificate_url": d.incorporation_certificate_url,
            "pan_photo_url": d.pan_photo_url, "aadhaar_number": d.aadhaar_number,
            "aadhaar_photo_url": d.aadhaar_photo_url,
            "cin_number": d.cin_number,
            "cin_certificate_url": d.cin_certificate_url,
            "company_logo_url": d.company_logo_url,
            "lat_long": d.lat_long
        }
        for d in dealers

    ]

@router.get("/logistics-partners")
async def list_all_partners(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all logistics partners (admin only)"""
    query = select(LogisticsPartner).offset(skip).limit(limit).order_by(LogisticsPartner.name)
    result = await db.execute(query)
    partners = result.scalars().all()
    return [
        {
            "id": p.id, "name": p.name, "contact_person": p.contact_person,
            "is_active": p.is_active
        }
        for p in partners
    ]

@router.get("/platform-partners")
async def list_platform_partners(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List platform partners for dealer assignment (admin)"""
    from models.partner import Partner
    result = await db.execute(select(Partner))
    partners = result.scalars().all()
    return [
        {
            "id": p.id,
            "partner_name": p.partner_name,
            "city": p.city,
            "state": p.state
        }
        for p in partners
    ]

@router.get("/logistics-partners/balances")
async def get_logistics_balances(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get COD balance (un-remitted cash) for each logistics partner"""
    # 1. Fetch all partners
    partners_res = await db.execute(select(LogisticsPartner))
    partners = partners_res.scalars().all()
    
    results = []
    for p in partners:
        # 2. Sum UNSETTLED collected COD (Delivered items where logistics_remittance_id is NULL)
        cod_query = (
            select(func.sum(OrderItem.quantity * OrderItem.price))
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.logistics_partner_id == p.id)
            .where(func.lower(OrderItem.status) == "delivered")
            .where(func.lower(Order.payment_method) == "cod")
            .where(OrderItem.logistics_remittance_id.is_(None))
        )
        collected_res = await db.execute(cod_query)
        unsettled_cash = collected_res.scalar() or 0.0
        
        # 3. Sum total remittances currently "Pending" (initiated but not confirmed)
        pending_remit_query = (
            select(func.sum(LogisticsRemittance.amount))
            .where(LogisticsRemittance.logistics_partner_id == p.id)
            .where(LogisticsRemittance.status == "pending")
        )
        remit_res = await db.execute(pending_remit_query)
        pending_remittance = remit_res.scalar() or 0.0
        
        results.append({
            "partner_id": p.id,
            "partner_name": p.name,
            "total_collected": unsettled_cash, # This is specifically UNSETTLED cash now
            "total_remitted_pending": pending_remittance,
            "pending_balance": max(0, unsettled_cash - pending_remittance)
        })
        
    return results

@router.get("/logistics-partners/{partner_id}/unsettled-orders")
async def list_unsettled_orders(
    partner_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List cod delivered items that haven't been settled yet for a partner"""
    from sqlalchemy.orm import selectinload
    
    query = (
        select(OrderItem)
        .options(selectinload(OrderItem.order).selectinload(Order.customer))
        .join(Order, OrderItem.order_id == Order.id)
        .where(OrderItem.logistics_partner_id == partner_id)
        .where(func.lower(OrderItem.status) == "delivered")
        .where(func.lower(Order.payment_method) == "cod")
        .where(OrderItem.logistics_remittance_id.is_(None))
        .order_by(OrderItem.delivered_at.desc())
    )
    res = await db.execute(query)
    items = res.scalars().all()
    
    return [
        {
            "id": items.id,
            "order_number": items.order.order_number or f"ORD-{items.order.id}",
            "customer_name": items.order.customer.full_name if items.order.customer else "Unknown",
            "amount": items.quantity * items.price,
            "delivered_at": items.delivered_at
        }
        for items in items
    ]

@router.get("/dealers/{dealer_id}/logistics")
async def list_dealer_logistics(
    dealer_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List logistics partners mapped to a specific dealer"""
    from sqlalchemy.orm import selectinload
    res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).options(selectinload(Dealer.logistics_partners)).where(Dealer.id == dealer_id))
    dealer = res.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
        
    return [
        {
            "id": p.id, "name": p.name, "contact_person": p.contact_person,
            "is_active": p.is_active
        }
        for p in dealer.logistics_partners
    ]

@router.post("/dealers/{dealer_id}/logistics/{partner_id}")
async def map_logistics_to_dealer(
    dealer_id: UUID,
    partner_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Map a logistics partner to a dealer"""
    from sqlalchemy.orm import selectinload
    # check dealer
    res_d = await db.execute(select(Dealer).where(Dealer.is_deleted == False).options(selectinload(Dealer.logistics_partners)).where(Dealer.id == dealer_id))
    dealer = res_d.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
    
    # check partner
    res_p = await db.execute(select(LogisticsPartner).where(LogisticsPartner.id == partner_id))
    partner = res_p.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Logistics partner not found")
        
    if partner not in dealer.logistics_partners:
        dealer.logistics_partners.append(partner)
        await db.commit()
        
    return {"message": "Mapped successfully"}

@router.delete("/dealers/{dealer_id}/logistics/{partner_id}")
async def unmap_logistics_from_dealer(
    dealer_id: UUID,
    partner_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Remove mapping between a logistics partner and a dealer"""
    from sqlalchemy.orm import selectinload
    res_d = await db.execute(select(Dealer).where(Dealer.is_deleted == False).options(selectinload(Dealer.logistics_partners)).where(Dealer.id == dealer_id))
    dealer = res_d.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
        
    res_p = await db.execute(select(LogisticsPartner).where(LogisticsPartner.id == partner_id))
    partner = res_p.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Logistics partner not found")
        
    if partner in dealer.logistics_partners:
        dealer.logistics_partners.remove(partner)
        await db.commit()
        
    return {"message": "Unmapped successfully"}
@router.put("/dealers/{dealer_id}/toggle-active")
async def toggle_dealer_active(
    dealer_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Toggle dealer active status (admin only)"""
    res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
    dealer = res.scalar_one_or_none()
    if not dealer: raise HTTPException(status_code=404, detail="Dealer not found")
    dealer.is_active = not dealer.is_active
    await db.commit()
    await db.refresh(dealer)
    return {"message": f"Dealer is now {'active' if dealer.is_active else 'inactive'}", "is_active": dealer.is_active}
@router.get("/helpdesk-supervisors")
async def list_helpdesk_supervisors(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of helpdesk supervisors"""
    res = await db.execute(select(User).where(User.role == UserRole.PARTNER_HELPDESK_SUPERVISOR, User.is_active == True))
    users = res.scalars().all()
    return [{"id": u.id, "full_name": u.full_name or u.email} for u in users]

@router.get("/helpdesk-managers")
async def list_helpdesk_managers(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of helpdesk managers"""
    res = await db.execute(select(User).where(User.role == UserRole.PARTNER_HELPDESK_MANAGER, User.is_active == True))
    users = res.scalars().all()
    return [{"id": u.id, "full_name": u.full_name or u.email} for u in users]

@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: AdminUserCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new user (Admin only)"""
    res = await db.execute(select(User).where(User.email == user_in.email, User.is_active == True))
    if res.scalar_one_or_none(): raise HTTPException(status_code=400, detail="Email already registered")
    user_data = user_in.model_dump()
    password = user_data.pop("password")
    db_user = User(**user_data, password_hash=get_password_hash(password))
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    user_in: AdminUserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user details (Admin only)"""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["password_hash"] = get_password_hash(update_data["password"])
        del update_data["password"]
        
    # Prevent unique constraint violations for empty strings
    if "employee_id" in update_data and update_data["employee_id"] == "":
        update_data["employee_id"] = None
    if "phone" in update_data and update_data["phone"] == "":
        update_data["phone"] = None
    if "email" in update_data and update_data["email"] == "":
        update_data["email"] = None
        
    for field, value in update_data.items(): setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user (Admin only)"""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id: raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await db.delete(user)
    await db.commit()
    return {"message": "User deleted successfully"}

@router.get("/products")
async def list_all_products(
    skip: int = 0, limit: int = 50, dealer_id: UUID = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all products (admin only)"""
    from sqlalchemy.orm import selectinload
    query = select(Product).options(selectinload(Product.dealer))
    if dealer_id: query = query.where(Product.dealer_id == dealer_id)
    result = await db.execute(query.offset(skip).limit(limit))
    products = result.scalars().all()
    return [
        {
            "id": p.id, "name": p.name, "price": p.selling_price or p.dealer_price, "mrp": p.mrp, "stock": getattr(p, 'stock', 0),
            "dealer_id": p.dealer_id, "dealer_name": p.dealer.business_name if p.dealer else None,
            "is_approved": p.is_approved, "created_at": p.created_at
        } for p in products
    ]

@router.put("/dealers/{dealer_id}/approve")
async def approve_dealer(
    dealer_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approve dealer (admin only)"""
    res = await db.execute(
        select(Dealer).where(Dealer.is_deleted == False)
        .options(selectinload(Dealer.user))
        .where(Dealer.id == dealer_id)
    )
    dealer = res.scalar_one_or_none()
    if not dealer: raise HTTPException(status_code=404, detail="Dealer not found")
    
    # Extract email and business name before committing, as commit expires attributes
    dealer_email = dealer.user.email if (dealer.user and dealer.user.email) else None
    business_name = dealer.business_name
    
    dealer.is_approved = True
    dealer.access_status = 'active'
    dealer.profile_status = 'completed'

    # Auto-create Default Hub if none exists
    from models.hub import DeliveryHub
    hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.dealer_id == dealer.id))
    existing_hub = hub_res.scalars().first()
    if not existing_hub:
        default_hub = DeliveryHub(
            dealer_id=dealer.id,
            name="Primary Warehouse",
            address=dealer.business_address or "Head Office",
            city=dealer.city,
            state=dealer.state,
            state_id=dealer.state_id,
            country_id=dealer.country_id,
            pincode=dealer.pincode,
            lat_long=dealer.lat_long,
            phone=dealer.business_phone,
            is_active=True,
            is_showroom=False,
            hub_type="Warehouse"
        )
        db.add(default_hub)

    await db.commit()
    
    # Send email notification
    if dealer_email:
        from services.notification import EmailService
        await EmailService.send_dealer_status_notification(
            to_email=dealer_email,
            business_name=business_name,
            approved=True
        )
        
    return {"message": "Dealer approved successfully", "is_approved": True}

class RejectReasonPayload(BaseModel):
    reason: str

@router.put("/dealers/{dealer_id}/reject")
async def reject_dealer(
    dealer_id: UUID, payload: RejectReasonPayload,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reject dealer (admin only)"""
    res = await db.execute(
        select(Dealer).where(Dealer.is_deleted == False)
        .options(selectinload(Dealer.user))
        .where(Dealer.id == dealer_id)
    )
    dealer = res.scalar_one_or_none()
    if not dealer: raise HTTPException(status_code=404, detail="Dealer not found")
    
    # Extract email and business name before committing, as commit expires attributes
    dealer_email = dealer.user.email if (dealer.user and dealer.user.email) else None
    business_name = dealer.business_name
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_reason = f"[{timestamp}] {payload.reason}"
    
    dealer.is_approved = False
    dealer.access_status = 'reject'
    dealer.profile_status = 'draft'
    
    if dealer.reject_reason:
        dealer.reject_reason = f"{dealer.reject_reason}\n{new_reason}"
    else:
        dealer.reject_reason = new_reason
        
    await db.commit()
    
    # Send email notification
    if dealer_email:
        from services.notification import EmailService
        await EmailService.send_dealer_status_notification(
            to_email=dealer_email,
            business_name=business_name,
            approved=False,
            reason=payload.reason
        )
        
    return {"message": "Dealer rejected", "is_approved": False}

@router.put("/products/{product_id}/approve", tags=["products"])
async def approve_product(
    product_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approve a product (admin only)"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.is_approved = True
    product_name = product.name
    product_id = product.id
    
    await db.commit()
    
    return {"message": f"Product '{product_name}' approved successfully", "id": product_id}

class RejectProductRequest(BaseModel):
    reason: str

@router.put("/products/{product_id}/reject", tags=["products"])
async def reject_product(
    product_id: UUID,
    payload: RejectProductRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reject a product (admin only)"""
    from datetime import datetime
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.is_approved = False
    
    # Track rejection reason
    current_reasons = list(product.reject_reasons) if product.reject_reasons else []
    current_reasons.append({
        "date": datetime.utcnow().isoformat(),
        "reason": payload.reason
    })
    product.reject_reasons = current_reasons
    
    product_name = product.name
    product_id = product.id
    
    await db.commit()
    
    return {"message": f"Product '{product_name}' rejected", "id": product_id}

@router.get("/riders", response_model=List[RiderSchema])
async def list_all_riders(
    skip: int = 0, limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all delivery riders (admin only)"""
    result = await db.execute(
        select(DeliveryRider, User.email)
        .join(User, DeliveryRider.user_id == User.id)
        .offset(skip).limit(limit)
    )
    riders_data = []
    for rider, email in result.all():
        d = rider.__dict__.copy()
        d["user_email"] = email
        riders_data.append(d)
    return riders_data

@router.put("/riders/{rider_id}", response_model=RiderSchema)
async def update_rider(
    rider_id: int, rider_data: RiderUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update rider profile (admin only)"""
    res = await db.execute(select(DeliveryRider).where(DeliveryRider.id == rider_id))
    rider = res.scalar_one_or_none()
    if not rider: raise HTTPException(status_code=404, detail="Rider not found")
    for key, value in rider_data.model_dump(exclude_unset=True).items(): setattr(rider, key, value)
    await db.commit()
    await db.refresh(rider)
    return rider

@router.post("/dealers", status_code=status.HTTP_201_CREATED)
async def create_dealer(
    dealer_in: DealerAdminCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new dealer (Admin only)"""
    res = await db.execute(select(User).where(User.email == dealer_in.email, User.is_active == True))
    if res.scalar_one_or_none(): raise HTTPException(status_code=400, detail="User email already exists")
    
    if dealer_in.business_phone:
        res_phone = await db.execute(select(User).where(User.phone == dealer_in.business_phone))
        if res_phone.scalar_one_or_none(): raise HTTPException(status_code=400, detail="Phone number already exists")

    try:
        db_user = User(
            email=dealer_in.email,
            password_hash=get_password_hash(dealer_in.password),
            full_name=dealer_in.full_name,
            phone=dealer_in.business_phone,
            role=UserRole.DEALER,
            is_active=True
        )
        db.add(db_user)
        await db.flush()
        db_dealer = Dealer(
            user_id=db_user.id,
            business_name=dealer_in.business_name,
            business_address=dealer_in.business_address,
            gst_number=dealer_in.gst_number,
            pan_number=dealer_in.pan_number,
            aadhaar_number=dealer_in.aadhaar_number,
            country_id=dealer_in.country_id,
            state_id=dealer_in.state_id,
            partner_id=dealer_in.partner_id,
            city=dealer_in.city,
            state=dealer_in.state,
            pincode=dealer_in.pincode,
            lat_long=dealer_in.lat_long,
            bank_name=dealer_in.bank_name,
            account_number=dealer_in.account_number,
            ifsc_code=dealer_in.ifsc_code,
            business_phone=dealer_in.business_phone,
            company_photo_url=dealer_in.company_photo_url,
            gst_certificate_url=dealer_in.gst_certificate_url,
            incorporation_certificate_url=dealer_in.incorporation_certificate_url,
            pan_photo_url=dealer_in.pan_photo_url,
            aadhaar_photo_url=dealer_in.aadhaar_photo_url,
            cin_number=dealer_in.cin_number,
            cin_certificate_url=dealer_in.cin_certificate_url,
            company_logo_url=dealer_in.company_logo_url,
            signature_image_url=dealer_in.signature_image_url,
            is_auction_enabled=dealer_in.is_auction_enabled,
            access_status='active', is_approved=True, profile_status='complete', is_active=True
        )
        db.add(db_dealer)
        await db.flush()
        dealer_id = db_dealer.id
        db_user.dealer_id = dealer_id

        # Auto-create Default Hub for the new dealer
        from models.hub import DeliveryHub
        default_hub = DeliveryHub(
            dealer_id=dealer_id,
            name="Primary Warehouse",
            address=dealer_in.business_address or "Head Office",
            city=dealer_in.city,
            state=dealer_in.state,
            state_id=dealer_in.state_id,
            country_id=dealer_in.country_id,
            pincode=dealer_in.pincode,
            phone=dealer_in.business_phone,
            is_active=True,
            is_showroom=False,
            hub_type="Warehouse"
        )
        db.add(default_hub)

        await db.commit()
        return {"message": "Dealer created successfully", "id": dealer_id}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/dealers/{dealer_id}")
async def update_dealer_profile(
    dealer_id: UUID, dealer_in: DealerAdminUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update dealer profile (Admin only)"""
    res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
    dealer = res.scalar_one_or_none()
    if not dealer: raise HTTPException(status_code=404, detail="Dealer profile not found")
    update_data = dealer_in.model_dump(exclude_unset=True)
    print(f"DEBUG: Updating dealer {dealer_id} with data: {update_data}")
    # Handle user model updates if provided
    if "full_name" in update_data:
        full_name = update_data.pop("full_name")
        await db.refresh(dealer, attribute_names=["user"])
        if dealer.user: dealer.user.full_name = full_name
    try:
        for field, value in update_data.items(): setattr(dealer, field, value)
        await db.commit()
        return {"message": "Dealer profile synchronized successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/dealers/{dealer_id}")
async def delete_dealer(
    dealer_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a dealer if no products are created (Admin only)"""
    res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
    dealer = res.scalar_one_or_none()
    if not dealer: raise HTTPException(status_code=404, detail="Dealer not found")
    
    # Check if dealer has created any products
    product_count = await db.execute(select(func.count(Product.id)).where(Product.dealer_id == dealer_id))
    if product_count.scalar() > 0:
        dealer.is_deleted = True
        from sqlalchemy import update
        await db.execute(update(User).where(User.dealer_id == dealer_id).values(is_active=False))
        await db.commit()
        return {"message": "Dealer soft-deleted successfully because they have products. All related users have been deactivated."}
        
    # Break the circular foreign key dependency for all associated users
    users_res = await db.execute(select(User).where(User.dealer_id == dealer_id))
    associated_users = users_res.scalars().all()
    
    for u in associated_users:
        u.dealer_id = None
    await db.flush()
            
    # Delete the dealer now that no user references it via dealer_id
    await db.delete(dealer)
    await db.flush()
    
    # Delete all associated users
    for u in associated_users:
        await db.delete(u)
        
    await db.commit()
            
    return {"message": "Dealer deleted successfully"}

@router.get("/remittances", response_model=List[RemittanceResponse])
async def list_all_remittances(
    skip: int = 0, limit: int = 50,
    status: Optional[str] = None,
    logistics_partner_id: Optional[int] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all remittances from logistics partners (Admin only)"""
    query = select(LogisticsRemittance).order_by(LogisticsRemittance.created_at.desc())
    if status and status != 'all':
        query = query.where(LogisticsRemittance.status == status.lower())
    if logistics_partner_id:
        query = query.where(LogisticsRemittance.logistics_partner_id == logistics_partner_id)
        
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    remittances = result.scalars().all()
    
    # Enrich with order numbers
    enriched_remittances = []
    for r in remittances:
        # Fetch order numbers linked to this remittance
        items_query = select(Order.order_number).join(OrderItem, OrderItem.id == OrderItem.id).where(OrderItem.order_id == Order.id).where(OrderItem.logistics_remittance_id == r.id).distinct()
        # Wait, the join was slightly wrong in my head.
        items_query = (
            select(Order.order_number)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.logistics_remittance_id == r.id)
            .distinct()
        )
        items_res = await db.execute(items_query)
        order_numbers = items_res.scalars().all()
        
        # We need to return a dict or object that matches RemittanceResponse
        r_dict = {
            "id": r.id,
            "logistics_partner_id": r.logistics_partner_id,
            "amount": r.amount,
            "status": r.status,
            "reference_no": r.reference_no,
            "payment_method": r.payment_method,
            "payment_date": r.payment_date,
            "notes": r.notes,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "confirmed_at": r.confirmed_at,
            "confirmed_by_admin_id": r.confirmed_by_admin_id,
            "order_numbers": order_numbers
        }
        enriched_remittances.append(r_dict)
        
    return enriched_remittances

@router.put("/remittances/{remittance_id}/status", response_model=RemittanceResponse)
async def update_remittance_status(
    remittance_id: int,
    payload: RemittanceStatusUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update remittance status (Admin only)"""
    res = await db.execute(select(LogisticsRemittance).where(LogisticsRemittance.id == remittance_id))
    remittance = res.scalar_one_or_none()
    if not remittance:
        raise HTTPException(status_code=404, detail="Remittance not found")
        
    valid_statuses = ["pending", "completed", "rejected"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid_statuses)}")
        
    remittance.status = payload.status
    if payload.status == "completed":
        from datetime import datetime, timezone
        remittance.confirmed_at = datetime.now(timezone.utc)
        remittance.confirmed_by_admin_id = current_user.id
        
        # When remittance is completed, all linked order items are officially settled (paid)
        await db.execute(
            update(OrderItem)
            .where(OrderItem.logistics_remittance_id == remittance.id)
            .values(payment_status="paid")
        )
    elif payload.status == "rejected":
        # If rejected, decouple the order items so they can be remitted again
        await db.execute(
            update(OrderItem)
            .where(OrderItem.logistics_remittance_id == remittance.id)
            .values(logistics_remittance_id=None)
        )
        
    await db.commit()
    await db.refresh(remittance)
    return remittance

@router.get("/recharge/stats")
async def get_admin_recharge_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get overall recharge statistics (Admin only)"""
    from datetime import datetime
    
    # Combined efficiency query using conditional aggregation
    stats_query = select(
        func.sum(case((RechargeTransaction.status == RechargeStatus.SUCCESS, RechargeTransaction.amount), else_=0)).label("revenue"),
        func.count(RechargeTransaction.id).label("total_count"),
        func.sum(case((RechargeTransaction.status == RechargeStatus.SUCCESS, 1), else_=0)).label("success_count"),
        func.sum(case((RechargeTransaction.status == RechargeStatus.FAILED, 1), else_=0)).label("failed_count"),
        func.sum(case((RechargeTransaction.status.in_([RechargeStatus.PENDING, RechargeStatus.PROCESSING]), 1), else_=0)).label("pending_count")
    )
    
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
            stats_query = stats_query.where(RechargeTransaction.created_at >= sd)
        except ValueError: pass
        
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace("Z", "+00:00")).replace(tzinfo=None)
            stats_query = stats_query.where(RechargeTransaction.created_at <= ed)
        except ValueError: pass

    res = await db.execute(stats_query)
    row = res.one()

    return {
        "revenue": float(row.revenue or 0),
        "count": int(row.total_count or 0),
        "success": int(row.success_count or 0),
        "failed": int(row.failed_count or 0),
        "pending": int(row.pending_count or 0)
    }

@router.get("/recharge/transactions")
async def list_admin_recharge_transactions(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all recharge transactions (Admin only)"""
    from datetime import datetime
    query = select(RechargeTransaction).order_by(RechargeTransaction.created_at.desc())
    
    if status and status != 'all':
        query = query.where(RechargeTransaction.status == status.lower())
    
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.where(RechargeTransaction.created_at >= sd)
        except ValueError: pass
        
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.where(RechargeTransaction.created_at <= ed)
        except ValueError: pass
        
    query = query.offset(skip).limit(limit)
    result = await db.execute(query.options(selectinload(RechargeTransaction.customer)))
    transactions = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "user_id": t.customer_id,
            "user_name": t.customer.full_name if t.customer else "N/A",
            "mobile_number": t.mobile_number,
            "operator": t.operator,
            "circle": t.circle,
            "amount": t.amount,
            "status": t.status.value if hasattr(t.status, 'value') else t.status,
            "provider_reference": t.provider_reference_id,
            "message": t.api_response_message,
            "created_at": t.created_at
        }
        for t in transactions
    ]


@router.get("/orders/{order_id}/dealer-fee-invoice/pdf")
async def download_admin_order_fee_invoice_pdf(
    order_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Admin endpoint to download the Platform Fee Tax Invoice issued to the dealer for an order."""
    from fastapi.responses import StreamingResponse
    from services.invoice_pdf import generate_dealer_fee_invoice_pdf
    from models.partner import Partner
    from models.billing_slab import BillingSlab
    from models.order import Order
    from models.order_item import OrderItem

    query = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(Order.items).selectinload(OrderItem.logistics_partner),
            selectinload(Order.shipping_address)
        )
    )
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    dealer = None
    if order.items and order.items[0].product and order.items[0].product.dealer:
        dealer = order.items[0].product.dealer
    else:
        raise HTTPException(status_code=400, detail="Could not resolve dealer for this order")

    partner_res = await db.execute(select(Partner).where(Partner.is_active == True).limit(1))
    partner = partner_res.scalars().first()

    mkt_sac = "996111"
    log_sac = "996812"
    try:
        res_mkt = await db.execute(
            select(BillingSlab.sac_hsn_code)
            .where(BillingSlab.category_key == 'marketplace', BillingSlab.is_active == True, BillingSlab.sac_hsn_code.isnot(None))
            .limit(1)
        )
        found_mkt = res_mkt.scalars().first()
        if found_mkt:
            mkt_sac = found_mkt

        res_log = await db.execute(
            select(BillingSlab.sac_hsn_code)
            .where(BillingSlab.category_key == 'logistics', BillingSlab.is_active == True, BillingSlab.sac_hsn_code.isnot(None))
            .limit(1)
        )
        found_log = res_log.scalars().first()
        if found_log:
            log_sac = found_log
    except Exception:
        pass

    pdf_buffer = generate_dealer_fee_invoice_pdf(
        order=order,
        dealer=dealer,
        items=order.items,
        partner=partner,
        marketplace_sac=mkt_sac,
        logistics_sac=log_sac
    )

    filename = f"Admin_Fee_Invoice_{order.order_number or order.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )

