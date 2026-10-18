from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Union
from datetime import datetime, timezone, timedelta
import string
import random

from core.database import get_db
from models.user import User, UserRole
from models.customer_user import CustomerUser
from models.support_ticket import (
    SupportTicket, TicketMessage, TicketStatus, TicketStage, TicketSLAStatus,
    TicketType, TicketPriority, TicketSource
)
from models.cart import OrderItem, Order
from models.dealer import Dealer
from models.product import Product, Category
from models.payment import Payment, PaymentWebhook
from models.audit import AuditLog
from models.address import Address
from models.order_return import OrderReturn
from models.settlement import Settlement, SettlementItem
from models.logistics_partner import LogisticsPartner
from models.delivery_rider import DeliveryRider
from services.return_policy_service import get_effective_protection_window
from services.configuration_service import get_settlement_configuration

from schemas.support_ticket import (
    SupportTicketCreate, SupportTicketResponse, CustomerSupportTicketResponse,
    TicketMessageCreate, TicketMessageResponse,
    TicketStatusUpdate, TicketPriorityUpdate, TicketAssignUpdate, TicketFeedbackCreate, TicketBulkAssign,
    TicketEscalateCreate, TicketReturnCreate, OperatorTicketCreate, DepartmentActionUpdate,
    OrderContextResponse, OrderItemContext,
    OrderLifecycleEvent, RiderDetailsContext, DeliveryAttemptRecord, ProofOfDeliveryContext,
    CustomerOrderPricingBreakdown, CODVerificationContext,
    LogisticsInvestigationContext, FinanceInvestigationContext,
    DealerProductInvestigationContext, TechnologyInvestigationContext,
    DepartmentInvestigationResponse,
    PRE_DELIVERY_REASONS, DELIVERED_REASONS, POST_POLICY_REASONS, PROFILE_REASONS, VALID_DEPARTMENTS
)
from core.permissions import get_current_active_user, require_admin

router = APIRouter()

SPECIALIST_ROLE_DEPT_MAP = {
    UserRole.PARTNER_FINANCE_SPECIALIST: "finance",
    UserRole.PARTNER_LOGISTICS_SPECIALIST: "logistics",
    UserRole.PARTNER_TECH_SUPPORT: "technology",
}

def get_user_specialist_dept(current_user: User) -> Optional[str]:
    if current_user.role in SPECIALIST_ROLE_DEPT_MAP:
        return SPECIALIST_ROLE_DEPT_MAP[current_user.role]
    if "dealer" in (current_user.email or "").lower() and current_user.role in [UserRole.PARTNER_BACKOFFICE, UserRole.DEALER, UserRole.DEALER_MANAGER]:
        return "dealer"
    return None

def get_user_authorized_departments(user: User) -> List[str]:
    """Determine which department investigation views the user is authorized to inspect"""
    role = getattr(user, "role", None)
    if role in [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.PARTNER_BACKOFFICE, UserRole.PARTNER_SUPPORT_MANAGER]:
        return ["logistics", "finance", "dealer", "technology"]
    if role == UserRole.PARTNER_LOGISTICS_SPECIALIST:
        return ["logistics"]
    if role == UserRole.PARTNER_FINANCE_SPECIALIST:
        return ["finance"]
    if role == UserRole.PARTNER_TECH_SUPPORT:
        return ["technology"]
    if role in [UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.PARTNER_CATALOG_MANAGER]:
        return ["dealer"]
    return []

def generate_ticket_number():
    chars = string.ascii_uppercase + string.digits
    return "TKT-" + ''.join(random.choices(chars, k=6))

def serialize_customer_ticket(ticket: SupportTicket) -> CustomerSupportTicketResponse:
    visible_messages = [
        TicketMessageResponse.model_validate(m)
        for m in (getattr(ticket, 'messages', None) or [])
        if not getattr(m, 'is_internal_note', False)
    ]
    return CustomerSupportTicketResponse(
        id=getattr(ticket, 'id', 0) or 0,
        ticket_number=getattr(ticket, 'ticket_number', '') or '',
        customer_id=getattr(ticket, 'customer_id', 0) or 0,
        order_id=getattr(ticket, 'order_id', None),
        order_item_id=getattr(ticket, 'order_item_id', None),
        product_id=getattr(ticket, 'product_id', None),
        subject=getattr(ticket, 'subject', '') or '',
        description=getattr(ticket, 'description', '') or '',
        ticket_type=getattr(ticket, 'ticket_type', TicketType.OTHERS) or TicketType.OTHERS,
        complaint_reason=getattr(ticket, 'complaint_reason', None),
        priority=getattr(ticket, 'priority', TicketPriority.MEDIUM) or TicketPriority.MEDIUM,
        status=getattr(ticket, 'status', TicketStatus.OPEN) or TicketStatus.OPEN,
        source=getattr(ticket, 'source', TicketSource.WEBSITE) or TicketSource.WEBSITE,
        ticket_stage=getattr(ticket, 'ticket_stage', TicketStage.HELPDESK) or TicketStage.HELPDESK,
        sla_status=getattr(ticket, 'sla_status', TicketSLAStatus.ON_TRACK) or TicketSLAStatus.ON_TRACK,
        customer_feedback_rating=getattr(ticket, 'customer_feedback_rating', None),
        customer_feedback_comments=getattr(ticket, 'customer_feedback_comments', None),
        created_at=getattr(ticket, 'created_at', None),
        updated_at=getattr(ticket, 'updated_at', None),
        resolved_at=getattr(ticket, 'resolved_at', None),
        resolved_by_user_id=getattr(ticket, 'resolved_by_user_id', None),
        attachments=getattr(ticket, 'attachments', None) or [],
        messages=visible_messages
    )

# Helper to validate complaint reasons
def validate_complaint_reason(reason: Optional[str], is_delivered: bool, is_expired: bool, has_item: bool):
    if not reason:
        return
    norm = reason.strip().lower()
    
    if has_item:
        if is_expired:
            allowed = [r.lower() for r in POST_POLICY_REASONS]
            if norm not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid complaint reason for out-of-warranty item. Allowed: {POST_POLICY_REASONS}"
                )
        elif is_delivered:
            allowed = [r.lower() for r in DELIVERED_REASONS]
            if norm not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid complaint reason for delivered item. Allowed: {DELIVERED_REASONS}"
                )
        else:
            allowed = [r.lower() for r in PRE_DELIVERY_REASONS]
            if norm not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid complaint reason for undelivered item. Allowed: {PRE_DELIVERY_REASONS}"
                )
    else:
        allowed = [r.lower() for r in PROFILE_REASONS]
        if norm not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid general complaint reason. Allowed: {PROFILE_REASONS}"
            )

# --- CUSTOMER ENDPOINTS ---

@router.post("/", response_model=CustomerSupportTicketResponse, tags=["support"])
async def create_ticket(
    ticket_in: SupportTicketCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Customer: Create a support ticket or raise a contextual complaint"""
    if current_user.role != "customer" and getattr(current_user, "is_customer", False) is False and getattr(current_user, "role", "") != UserRole.CUSTOMER:
        raise HTTPException(status_code=403, detail="Only customers can create tickets through this endpoint")
        
    dealer_id = None
    partner_id = None
    order_id = ticket_in.order_id
    product_id = None
    order_item = None
    order = None
    
    if ticket_in.order_item_id:
        res = await db.execute(
            select(OrderItem, Order)
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.id == ticket_in.order_item_id, Order.customer_id == current_user.id)
            .options(selectinload(OrderItem.product).selectinload(Product.dealer))
        )
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Order item not found or does not belong to you")
        
        order_item, order = row
        order_id = order.id
        product_id = order_item.product_id
        prod_obj = order_item.product
        if not prod_obj and product_id:
            prod_res = await db.execute(select(Product).options(selectinload(Product.dealer)).where(Product.id == product_id))
            prod_obj = prod_res.scalar_one_or_none()

        if prod_obj:
            dealer_id = prod_obj.dealer_id
            if prod_obj.dealer:
                partner_id = prod_obj.dealer.partner_id
            elif dealer_id:
                dealer_res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
                dealer = dealer_res.scalar_one_or_none()
                if dealer:
                    partner_id = dealer.partner_id
        
        # Check delivery and return policy expiration
        is_delivered = bool(
            (order_item.status and order_item.status.lower() == "delivered") or
            (order.status and order.status.value.lower() == "delivered" if hasattr(order.status, "value") else str(order.status).lower() == "delivered")
        )
        is_expired = False
        
        if is_delivered:
            deliv_dt = order_item.delivered_at or getattr(order, "delivered_at", None)
            if deliv_dt:
                settlement_config = await get_settlement_configuration(db)
                window_days = get_effective_protection_window(order_item, product=prod_obj, global_config=settlement_config)
                
                # Check maturity
                now_utc = datetime.now(timezone.utc)
                if deliv_dt.tzinfo is None:
                    deliv_dt = deliv_dt.replace(tzinfo=timezone.utc)
                if now_utc > (deliv_dt + timedelta(days=window_days)):
                    is_expired = True

        validate_complaint_reason(ticket_in.complaint_reason, is_delivered=is_delivered, is_expired=is_expired, has_item=True)
    elif ticket_in.order_id:
        res = await db.execute(
            select(Order)
            .where(Order.id == ticket_in.order_id, Order.customer_id == current_user.id)
            .options(selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer))
        )
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found or does not belong to you")
            
        order_id = order.id
        if order.items:
            first_item = order.items[0]
            product_id = first_item.product_id
            prod_obj = first_item.product
            if not prod_obj and product_id:
                prod_res = await db.execute(select(Product).options(selectinload(Product.dealer)).where(Product.id == product_id))
                prod_obj = prod_res.scalar_one_or_none()
            if prod_obj:
                dealer_id = prod_obj.dealer_id
                if prod_obj.dealer:
                    partner_id = prod_obj.dealer.partner_id
                elif dealer_id:
                    dealer_res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
                    dealer = dealer_res.scalar_one_or_none()
                    if dealer:
                        partner_id = dealer.partner_id
                    
        is_delivered = bool(
            (order.status and (order.status.value.lower() == "delivered" if hasattr(order.status, "value") else str(order.status).lower() == "delivered"))
        )
        is_expired = False
        if is_delivered:
            deliv_dt = getattr(order, "delivered_at", None)
            if not deliv_dt and order.items:
                deliv_dt = order.items[0].delivered_at
            if deliv_dt:
                settlement_config = await get_settlement_configuration(db)
                window_days = settlement_config.return_window_days if settlement_config else 7
                now_utc = datetime.now(timezone.utc)
                if deliv_dt.tzinfo is None:
                    deliv_dt = deliv_dt.replace(tzinfo=timezone.utc)
                if now_utc > (deliv_dt + timedelta(days=window_days)):
                    is_expired = True
                    
        validate_complaint_reason(ticket_in.complaint_reason, is_delivered=is_delivered, is_expired=is_expired, has_item=True)
    else:
        validate_complaint_reason(ticket_in.complaint_reason, is_delivered=False, is_expired=False, has_item=False)

    now = datetime.utcnow()
    escalation_deadline = now + timedelta(hours=4) # 4 hours SLA for first response
    assigned_user_id = None
    
    # Auto-Assign logic: find active PARTNER_HELPDESK_OPERATOR with least open tickets
    helpdesk_users_res = await db.execute(
        select(User.id)
        .where(
            User.role == UserRole.PARTNER_HELPDESK_OPERATOR,
            User.is_active == True
        )
    )
    helpdesk_user_ids = helpdesk_users_res.scalars().all()
    if helpdesk_user_ids:
        counts_res = await db.execute(
            select(SupportTicket.assigned_user_id, func.count(SupportTicket.id))
            .where(SupportTicket.assigned_user_id.in_(helpdesk_user_ids), SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
            .group_by(SupportTicket.assigned_user_id)
        )
        counts = dict(counts_res.all())
        min_count = float('inf')
        for uid in helpdesk_user_ids:
            c = counts.get(uid, 0)
            if c < min_count:
                min_count = c
                assigned_user_id = uid
    
    new_ticket = SupportTicket(
        ticket_number=generate_ticket_number(),
        customer_id=current_user.id,
        dealer_id=dealer_id,
        partner_id=partner_id,
        order_id=order_id,
        order_item_id=ticket_in.order_item_id,
        product_id=product_id,
        subject=ticket_in.subject,
        description=ticket_in.description,
        ticket_type=ticket_in.ticket_type or TicketType.OTHERS,
        complaint_reason=ticket_in.complaint_reason,
        source=ticket_in.source or TicketSource.WEBSITE,
        ticket_stage=TicketStage.HELPDESK,
        status=TicketStatus.OPEN,
        assigned_user_id=assigned_user_id,
        escalation_deadline=escalation_deadline,
        attachments=ticket_in.attachments or [],
        device_info=ticket_in.device_info
    )
    db.add(new_ticket)
    await db.flush()
    ticket_id = new_ticket.id
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return serialize_customer_ticket(res.scalar_one())

# --- OPERATOR INTAKE ENDPOINT ---

@router.post("/operator-create", response_model=SupportTicketResponse, tags=["support"])
async def operator_create_ticket(
    ticket_in: OperatorTicketCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Helpdesk Operator / Admin: Log manual phone or email complaint on behalf of customer"""
    allowed_roles = [
        UserRole.PARTNER_HELPDESK_OPERATOR,
        UserRole.PARTNER_HELPDESK_SUPERVISOR,
        UserRole.PARTNER_HELPDESK_MANAGER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Only Helpdesk and Admin personnel can create tickets on behalf of customers")
        
    # Verify customer exists
    cust = None
    target_cust_id = ticket_in.customer_id

    if not target_cust_id and ticket_in.customer_identifier:
        ident = ticket_in.customer_identifier.strip()
        if ident.isdigit():
            target_cust_id = int(ident)
        else:
            cust_by_email = await db.execute(
                select(CustomerUser).where(
                    (CustomerUser.email == ident) | (CustomerUser.phone == ident)
                )
            )
            found_c = cust_by_email.scalar_one_or_none()
            if found_c:
                cust = found_c
                target_cust_id = found_c.id
            else:
                u_by_email = await db.execute(
                    select(User).where((User.email == ident) | (User.phone_number == ident))
                )
                found_u = u_by_email.scalar_one_or_none()
                if found_u:
                    target_cust_id = found_u.id

    if target_cust_id and not cust:
        cust_res = await db.execute(
            select(CustomerUser).where(CustomerUser.id == target_cust_id)
        )
        cust = cust_res.scalar_one_or_none()
        if not cust:
            u_res = await db.execute(select(User).where(User.id == target_cust_id))
            if not u_res.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Customer not found")

    if not target_cust_id:
        raise HTTPException(status_code=400, detail="Customer ID or Email/Phone identifier is required")
            
    dealer_id = None
    partner_id = None
    order_id = ticket_in.order_id
    product_id = None
    
    if ticket_in.order_item_id:
        res = await db.execute(
            select(OrderItem, Order)
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.id == ticket_in.order_item_id)
            .options(selectinload(OrderItem.product).selectinload(Product.dealer))
        )
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Order item not found")
        order_item, order = row
        if order.customer_id != target_cust_id:
            raise HTTPException(
                status_code=400,
                detail=f"Order item #{ticket_in.order_item_id} belongs to order #{order.id}, which does not belong to customer {target_cust_id}"
            )
        order_id = order.id
        product_id = order_item.product_id
        prod_obj = order_item.product
        if not prod_obj and product_id:
            prod_res = await db.execute(select(Product).options(selectinload(Product.dealer)).where(Product.id == product_id))
            prod_obj = prod_res.scalar_one_or_none()
        if prod_obj:
            dealer_id = prod_obj.dealer_id
            if prod_obj.dealer:
                partner_id = prod_obj.dealer.partner_id
            elif dealer_id:
                dealer_res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
                dealer = dealer_res.scalar_one_or_none()
                if dealer:
                    partner_id = dealer.partner_id
    elif ticket_in.order_id:
        order_res = await db.execute(
            select(Order).where(Order.id == ticket_in.order_id)
            .options(selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer))
        )
        order = order_res.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.customer_id != target_cust_id:
            raise HTTPException(
                status_code=400,
                detail=f"Order #{ticket_in.order_id} does not belong to customer {target_cust_id}"
            )
        if order.items:
            first_item = order.items[0]
            product_id = first_item.product_id
            prod_obj = first_item.product
            if not prod_obj and product_id:
                prod_res = await db.execute(select(Product).options(selectinload(Product.dealer)).where(Product.id == product_id))
                prod_obj = prod_res.scalar_one_or_none()
            if prod_obj:
                dealer_id = prod_obj.dealer_id
                if prod_obj.dealer:
                    partner_id = prod_obj.dealer.partner_id
                elif dealer_id:
                    dealer_res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
                    dealer = dealer_res.scalar_one_or_none()
                    if dealer:
                        partner_id = dealer.partner_id

    now = datetime.utcnow()
    escalation_deadline = now + timedelta(hours=4)
    assigned_user_id = current_user.id if current_user.role == UserRole.PARTNER_HELPDESK_OPERATOR else None

    new_ticket = SupportTicket(
        ticket_number=generate_ticket_number(),
        customer_id=target_cust_id,
        dealer_id=dealer_id,
        partner_id=partner_id,
        order_id=order_id,
        order_item_id=ticket_in.order_item_id,
        product_id=product_id,
        subject=ticket_in.subject,
        description=ticket_in.description,
        ticket_type=ticket_in.ticket_type or TicketType.OTHERS,
        complaint_reason=ticket_in.complaint_reason,
        priority=ticket_in.priority or TicketPriority.MEDIUM,
        source=ticket_in.source or TicketSource.PHONE,
        ticket_stage=TicketStage.HELPDESK,
        status=TicketStatus.OPEN,
        assigned_user_id=assigned_user_id,
        escalation_deadline=escalation_deadline,
        attachments=ticket_in.attachments or []
    )
    db.add(new_ticket)
    await db.flush()
    ticket_id = new_ticket.id
    await db.commit()

    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

# --- ORDER 360° INSPECTOR CONTEXT ENDPOINT ---

@router.get("/{ticket_id}/order-context", response_model=OrderContextResponse, tags=["support"])
async def get_order_context(
    ticket_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Helpdesk & Backoffice: Get complete 360° Order, Payment, Shipment, Return, and Settlement details for ticket"""
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if (current_user.role == "customer" or current_user.role == UserRole.CUSTOMER) and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view order context for this ticket")

    specialist_dept = get_user_specialist_dept(current_user)
    if specialist_dept:
        current_dept = ticket.assigned_department.lower().strip() if ticket.assigned_department else None
        if current_dept and current_dept != specialist_dept:
            raise HTTPException(status_code=403, detail="Not authorized to view order context for another department's tickets")
        
    if not ticket.order_id and not ticket.order_item_id:
        return OrderContextResponse(ticket_id=ticket.id)
        
    order = None
    if ticket.order_id:
        order_res = await db.execute(
            select(Order)
            .where(Order.id == ticket.order_id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.payment),
                selectinload(Order.shipping_address).selectinload(Address.state_rel),
                selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
                selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.category),
                selectinload(Order.items).selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
                selectinload(Order.items).selectinload(OrderItem.logistics_partner),
            )
        )
        order = order_res.scalar_one_or_none()
    elif ticket.order_item_id:
        item_res = await db.execute(
            select(OrderItem)
            .where(OrderItem.id == ticket.order_item_id)
            .options(
                selectinload(OrderItem.order).selectinload(Order.customer),
                selectinload(OrderItem.order).selectinload(Order.payment),
                selectinload(OrderItem.order).selectinload(Order.shipping_address).selectinload(Address.state_rel),
                selectinload(OrderItem.order).selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
                selectinload(OrderItem.order).selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.category),
                selectinload(OrderItem.order).selectinload(Order.items).selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
                selectinload(OrderItem.order).selectinload(Order.items).selectinload(OrderItem.logistics_partner),
                selectinload(OrderItem.product).selectinload(Product.dealer),
                selectinload(OrderItem.product).selectinload(Product.category),
                selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
                selectinload(OrderItem.logistics_partner)
            )
        )
        found_item = item_res.scalar_one_or_none()
        if found_item:
            order = found_item.order

    if not order:
        return OrderContextResponse(ticket_id=ticket.id, order_id=ticket.order_id)

    pm = order.payment

    # Shipping Address dict with distinct recipient identity
    addr_dict = None
    if order.shipping_address:
        addr = order.shipping_address
        addr_dict = {
            "recipient_name": getattr(addr, "full_name", None),
            "recipient_phone": getattr(addr, "phone", None),
            "address_line1": getattr(addr, "address_line1", None) or getattr(addr, "address", None),
            "address_line2": getattr(addr, "address_line2", None),
            "city": getattr(addr, "city", None),
            "state": (
                getattr(getattr(addr, "state_rel", None), "name", None)
                or (str(getattr(addr, "state_id", "")) if getattr(addr, "state_id", None) else None)
            ),
            "pincode": getattr(addr, "pincode", None),
            "country": getattr(addr, "country", "India") or "India",
        }

    # Customer info (buyer who placed order)
    cust_name = None
    cust_email = None
    cust_phone = None
    if order.customer:
        cust_name = order.customer.full_name
        cust_email = order.customer.email
        cust_phone = getattr(order.customer, "phone_number", None) or getattr(order.customer, "phone", None)
    elif getattr(order, "customer_name", None) or getattr(order, "customer_phone", None):
        cust_name = getattr(order, "customer_name", None)
        cust_phone = getattr(order, "customer_phone", None)

    # Base delivery status
    delivery_status = order.status.value if hasattr(order.status, "value") else str(order.status)

    # Items breakdown
    order_items_list = []
    selected_item_context = None

    settlement_config = await get_settlement_configuration(db)

    for itm in (order.items or []):
        prod = itm.product
        dealer = prod.dealer if prod else None
        
        # Calculate protection maturity
        mat_dt = None
        deliv = itm.delivered_at or (order.delivered_at if str(itm.status).lower() == "delivered" else None)
        if deliv:
            win = get_effective_protection_window(itm, product=prod, global_config=settlement_config)
            mat_dt = deliv + timedelta(days=win)
            
        r_name = None
        r_phone = None
        if itm.rider:
            r_name = itm.rider.user.full_name if itm.rider.user else None
            r_phone = itm.rider.phone_number
        lp_name = itm.logistics_partner.name if itm.logistics_partner else None
        item_courier = itm.courier_company

        item_attempts = getattr(itm, "delivery_attempts", 0) or 0

        item_mrp = getattr(prod, 'mrp', None) or getattr(itm, 'price', 0.0)
        item_selling_price = float(itm.price or 0.0)
        item_qty = itm.quantity or 1
        raw_disc = max(0.0, float(item_mrp - item_selling_price)) if item_mrp else 0.0
        disc_pct = int(round((raw_disc / float(item_mrp)) * 100)) if (item_mrp and item_mrp > 0) else 0

        item_ctx = OrderItemContext(
            id=itm.id,
            product_id=itm.product_id,
            product_name=prod.name if prod else "Unknown Product",
            product_image=(prod.images[0] if (prod and getattr(prod, 'images', None) and isinstance(prod.images, list) and len(prod.images) > 0) else getattr(prod, 'image_url', None)),
            category_name=prod.category.name if (prod and getattr(prod, 'category', None)) else None,
            quantity=item_qty,
            price=item_selling_price,
            mrp=float(item_mrp) if item_mrp is not None else None,
            discount_amount=round(raw_disc * item_qty, 2),
            discount_percentage=disc_pct,
            status=itm.status.value if hasattr(itm.status, 'value') else (str(itm.status) if itm.status is not None else None),
            delivered_at=deliv,
            return_window_matures_at=mat_dt,
            dealer_name=dealer.business_name if dealer else None,
            dealer_id=dealer.id if dealer else None,
            courier_company=item_courier,
            tracking_number=itm.tracking_number or order.tracking_number,
            tracking_url=itm.tracking_url,
            dispatch_date=itm.dispatch_date,
            estimated_delivery=itm.estimated_delivery or order.estimated_delivery,
            delivery_attempts=item_attempts,
            delivery_type=itm.delivery_type,
            reject_reason=itm.reject_reason,
            logistics_partner_name=lp_name,
            delivery_rider_name=r_name,
            delivery_rider_phone=r_phone
        )
        order_items_list.append(item_ctx)
        if ticket.order_item_id == itm.id:
            selected_item_context = item_ctx

    # Determine top-level delivery and tracking info
    ref_item = selected_item_context or (order_items_list[0] if order_items_list else None)

    top_logistics_name = ref_item.logistics_partner_name if ref_item else None
    top_courier_company = ref_item.courier_company if ref_item else None
    top_rider_name = ref_item.delivery_rider_name if ref_item else None
    top_rider_phone = ref_item.delivery_rider_phone if ref_item else None
    top_tracking_number = (ref_item.tracking_number if ref_item else None) or order.tracking_number
    top_tracking_url = ref_item.tracking_url if ref_item else None
    top_dispatch_date = ref_item.dispatch_date if ref_item else None
    top_estimated_delivery = (ref_item.estimated_delivery if ref_item else None) or order.estimated_delivery
    top_delivered_at = (ref_item.delivered_at if ref_item else None) or order.delivered_at
    top_delivery_attempts = (ref_item.delivery_attempts if ref_item else 0) or 0
    top_delivery_status = (ref_item.status if selected_item_context else None) or delivery_status

    # Returns record
    return_status = None
    return_reason = None
    return_res = await db.execute(
        select(OrderReturn)
        .where(
            or_(
                OrderReturn.order_id == order.id,
                OrderReturn.order_item_id == ticket.order_item_id if ticket.order_item_id else False
            )
        )
    )
    ret = return_res.scalars().first()
    if ret:
        return_status = ret.status.value if hasattr(ret.status, "value") else str(ret.status)
        return_reason = ret.reason

    # Settlement status and structured settlement info
    settlement_status = "Not generated"
    settlement_dict = None
    settle_item_res = await db.execute(
        select(SettlementItem, Settlement)
        .join(Settlement, SettlementItem.settlement_id == Settlement.id)
        .where(SettlementItem.order_id == order.id)
    )
    si_row = settle_item_res.first()
    if si_row:
        si, st = si_row
        st_status_str = st.status.value if hasattr(st.status, "value") else str(st.status)
        settlement_status = f"{st_status_str.upper()} (Settlement #{st.settlement_number or st.id})"
        settlement_dict = {
            "id": st.id,
            "settlement_number": st.settlement_number or f"STL-{st.id}",
            "status": st_status_str,
            "net_amount": float(getattr(si, "net_payable", 0.0) or getattr(st, "net_payable", 0.0) or 0.0),
            "is_l2_approved": getattr(st, "is_l2_approved", False),
            "l2_approved_at": getattr(st, "l2_approved_at", None),
        }

    # Tracking object for UI backward compatibility
    tracking_dict = {
        "courier_company": top_courier_company or top_logistics_name,
        "tracking_number": top_tracking_number,
        "tracking_url": top_tracking_url,
        "dispatch_date": top_dispatch_date,
        "delivery_date": top_delivered_at,
        "delivered_at": top_delivered_at,
        "estimated_delivery": top_estimated_delivery,
        "delivery_attempts": top_delivery_attempts,
        "status": top_delivery_status
    }

    # Build Order Lifecycle Timeline
    lifecycle_events = []

    # 1. Order Placed
    lifecycle_events.append(OrderLifecycleEvent(
        event_key="order_placed",
        event_title="Order Placed",
        timestamp=order.created_at,
        is_completed=True,
        is_current=False,
        description=f"Order #{order.order_number or order.id} placed by customer.",
        source="system"
    ))

    # 2. Payment
    payment_done = pm and str(pm.status).lower() in ("success", "paid")
    is_cod = str(order.payment_method).lower() == "cod"
    lifecycle_events.append(OrderLifecycleEvent(
        event_key="payment",
        event_title="Payment Confirmed" if payment_done else ("COD Order Placed" if is_cod else "Payment Pending"),
        timestamp=(pm.completed_at or pm.initiated_at) if pm else order.created_at,
        is_completed=payment_done or is_cod,
        is_current=False,
        description=f"Payment Method: {order.payment_method} (Gateway: {getattr(pm, 'payment_gateway', 'N/A') if pm else 'N/A'})",
        source="payment_gateway" if pm else "system"
    ))

    # 3. Dispatched / Shipped
    is_dispatched = bool(top_dispatch_date or (top_delivery_status and top_delivery_status.lower() in ("shipped", "dispatched", "out_for_delivery", "delivered")))
    lifecycle_events.append(OrderLifecycleEvent(
        event_key="dispatched",
        event_title="Package Dispatched",
        timestamp=top_dispatch_date,
        is_completed=is_dispatched,
        is_current=(top_delivery_status or "").lower() in ("shipped", "dispatched"),
        description=f"Handed to {top_courier_company or top_logistics_name or 'logistics'} (AWB: {top_tracking_number or 'Pending'})" if is_dispatched else "Package packing and preparation.",
        source="courier" if top_courier_company else "system"
    ))

    # 4. Out For Delivery
    is_ofd = bool(top_delivered_at or (top_delivery_status and top_delivery_status.lower() in ("out_for_delivery", "delivered")))
    lifecycle_events.append(OrderLifecycleEvent(
        event_key="out_for_delivery",
        event_title="Out for Delivery",
        timestamp=top_delivered_at if top_delivered_at and not top_dispatch_date else None,
        is_completed=is_ofd,
        is_current=(top_delivery_status or "").lower() == "out_for_delivery",
        description=f"Assigned to {top_rider_name or 'local courier delivery unit'}" if is_ofd else "Pending arrival at destination hub.",
        source="rider" if top_rider_name else "courier"
    ))

    # 5. Delivered / Failed
    is_delivered = bool(top_delivered_at or (top_delivery_status and top_delivery_status.lower() == "delivered"))
    is_failed_or_returned = bool((top_delivery_status and top_delivery_status.lower() in ("undelivered", "failed", "returned", "cancelled")) or order.cancellation_reason)

    if is_delivered:
        lifecycle_events.append(OrderLifecycleEvent(
            event_key="delivered",
            event_title="Delivered",
            timestamp=top_delivered_at,
            is_completed=True,
            is_current=True,
            description=f"Package delivered successfully.",
            source="rider" if top_rider_name else "courier"
        ))
    elif is_failed_or_returned:
        lifecycle_events.append(OrderLifecycleEvent(
            event_key="delivery_failed",
            event_title=f"Delivery {top_delivery_status.capitalize() if top_delivery_status else 'Failed'}",
            timestamp=order.cancelled_at or order.updated_at,
            is_completed=True,
            is_current=True,
            description=f"Reason: {order.cancellation_reason or (ref_item.reject_reason if ref_item else None) or 'Customer unavailable / maximum attempts exceeded'}",
            source="courier"
        ))
    else:
        lifecycle_events.append(OrderLifecycleEvent(
            event_key="delivered",
            event_title="Delivery Pending",
            timestamp=top_estimated_delivery,
            is_completed=False,
            is_current=False,
            description=f"Estimated delivery: {top_estimated_delivery.strftime('%d %b %Y') if top_estimated_delivery else 'In transit'}",
            source="system"
        ))

    # Build Rider Details Context
    rider_details_obj = None
    target_itm_with_rider = next((itm for itm in (order.items or []) if itm.rider and (ticket.order_item_id is None or itm.id == ticket.order_item_id)), None)
    if not target_itm_with_rider:
        target_itm_with_rider = next((itm for itm in (order.items or []) if itm.rider), None)

    if target_itm_with_rider and target_itm_with_rider.rider:
        r = target_itm_with_rider.rider
        rider_details_obj = RiderDetailsContext(
            rider_id=r.id,
            full_name=r.user.full_name if r.user else None,
            phone_number=r.phone_number,
            vehicle_type=r.vehicle_type,
            vehicle_number=r.vehicle_number,
            current_status=r.current_status,
            is_available=r.is_available,
            average_rating=float(r.average_rating or 0.0),
            total_reviews=r.total_reviews or 0,
            logistics_partner_name=target_itm_with_rider.logistics_partner.name if target_itm_with_rider.logistics_partner else None,
            business_name=r.business_name
        )

    # Build Delivery Attempt History
    attempt_history = []
    if top_delivery_attempts > 0:
        for att_idx in range(1, top_delivery_attempts + 1):
            is_last = (att_idx == top_delivery_attempts)
            attempt_history.append(DeliveryAttemptRecord(
                attempt_number=att_idx,
                attempt_timestamp=top_delivered_at if (is_last and is_delivered) else (order.updated_at or order.created_at),
                status="Delivered" if (is_last and is_delivered) else "Failed / Customer Unavailable",
                reason=(ref_item.reject_reason if is_last and ref_item else None) or ("Customer unreachable / Door locked" if not (is_last and is_delivered) else None),
                source="rider" if top_rider_name else "courier",
                notes=f"Attempt {att_idx} of 3"
            ))

    # Build Proof of Delivery Context
    pod_obj = ProofOfDeliveryContext(
        is_available=False,
        pod_type="courier_scan" if top_courier_company else ("rider_confirmation" if top_rider_name else None),
        recipient_name=addr_dict.get("recipient_name") if (addr_dict and is_delivered) else None,
        handover_timestamp=top_delivered_at if is_delivered else None,
        evidence_url=None,
        status_notes="Digital OTP / signature / photo proof not enabled on courier/rider channel. Only delivery timestamp and attempt logs are recorded."
    )

    # Calculate Customer Order Pricing Breakdown
    calc_total_mrp = sum(float((getattr(itm.product, 'mrp', None) or itm.price or 0.0)) * (itm.quantity or 1) for itm in (order.items or []))
    calc_selling_total = sum(float(itm.price or 0.0) * (itm.quantity or 1) for itm in (order.items or []))
    calc_disc_on_mrp = max(0.0, calc_total_mrp - calc_selling_total)
    persisted_coupon_disc = float(order.discount_amount or 0.0)
    persisted_delivery_charge = float(order.delivery_charge or 0.0)
    persisted_platform_fee = float(order.platform_fee_amount or 0.0)
    persisted_wallet_used = float(order.wallet_amount_used or 0.0)
    persisted_total = float(order.total_amount or 0.0)

    # Final customer order amount from persisted components
    expected_customer_total = round(calc_selling_total - persisted_coupon_disc - persisted_wallet_used + persisted_delivery_charge + persisted_platform_fee, 2)
    has_pricing_discrepancy = abs(expected_customer_total - round(persisted_total, 2)) > 0.05
    pricing_discrepancy_msg = None
    if has_pricing_discrepancy:
        pricing_discrepancy_msg = f"Discrepancy detected: Calculated customer total (₹{expected_customer_total:.2f}) differs from persisted order total (₹{persisted_total:.2f})."

    pricing_breakdown_obj = CustomerOrderPricingBreakdown(
        total_mrp=round(calc_total_mrp, 2),
        discount_on_mrp=round(calc_disc_on_mrp, 2),
        coupon_discount=round(persisted_coupon_disc, 2),
        total_savings=round(calc_disc_on_mrp + persisted_coupon_disc, 2),
        delivery_charge=round(persisted_delivery_charge, 2),
        platform_fee=round(persisted_platform_fee, 2),
        wallet_applied=round(persisted_wallet_used, 2),
        other_customer_charges=0.0,
        final_order_amount=round(persisted_total, 2),
        persisted_total_amount=round(persisted_total, 2),
        has_pricing_discrepancy=has_pricing_discrepancy,
        discrepancy_details=pricing_discrepancy_msg
    )

    # Calculate COD Verification Details
    is_order_cod = str(order.payment_method or '').lower() == 'cod'
    cod_verification_obj = None
    if is_order_cod:
        # Check if rider recorded payment method during task completion
        rider_coll_method = None
        has_rider_delivery_event = False
        for itm in (order.items or []):
            if getattr(itm, 'rider_payment_method', None):
                rider_coll_method = itm.rider_payment_method
            if str(getattr(itm, 'status', '')).lower() == 'delivered':
                has_rider_delivery_event = True

        # Check payment table
        pm_paid = pm and str(pm.status).lower() in ('success', 'paid')

        # Collection status logic:
        # If payment row has success OR rider marked payment method -> Collected
        # If delivered but no collection record -> Inconsistency / Discrepancy
        if pm_paid or rider_coll_method:
            cod_status = "COLLECTED"
            is_verified = True
            coll_amt = float(pm.amount if pm and pm.amount else persisted_total)
            coll_time = (pm.completed_at if pm and pm.completed_at else top_delivered_at)
            reconcile_msg = None
        elif is_delivered:
            cod_status = "UNVERIFIED_DELIVERED"
            is_verified = False
            coll_amt = None
            coll_time = None
            reconcile_msg = "Order marked DELIVERED but no cash/UPI collection record exists in payment gateway or rider handover log."
        else:
            cod_status = "PENDING_DELIVERY"
            is_verified = False
            coll_amt = None
            coll_time = None
            reconcile_msg = None

        cod_verification_obj = CODVerificationContext(
            is_cod=True,
            payment_method="Cash on Delivery (COD)",
            payment_status=pm.status.value if (pm and hasattr(pm.status, 'value')) else (str(pm.status) if pm else "pending"),
            cod_collection_status=cod_status,
            amount_to_collect=round(persisted_total, 2),
            amount_collected=round(coll_amt, 2) if coll_amt is not None else None,
            collected_at=coll_time,
            collected_by=top_rider_name or (f"Logistics Partner ({top_logistics_name})" if top_logistics_name else "Courier"),
            collected_method=rider_coll_method or (pm.payment_gateway if pm else None),
            is_verified_collected=is_verified,
            reconciliation_discrepancy=reconcile_msg
        )

    user_authorized_depts = get_user_authorized_departments(current_user)

    # 1. Logistics Investigation
    logistics_inv = None
    if "logistics" in user_authorized_depts:
        discrepancy = None
        if top_delivery_status and top_delivery_status.lower() == "delivered" and (top_delivery_attempts == 0 or not top_delivered_at):
            discrepancy = "Order marked DELIVERED but 0 delivery attempt events recorded."
        elif top_delivery_status and top_delivery_status.lower() in ("shipped", "dispatched", "out_for_delivery"):
            if top_estimated_delivery and top_estimated_delivery < datetime.utcnow():
                discrepancy = "Package is past estimated delivery date without terminal scan."

        shipment_exc = []
        if ret and getattr(ret, "pickup_attempts", 0) and ret.pickup_attempts > 1:
            shipment_exc.append(f"Return pickup delayed: {ret.pickup_attempts} attempts recorded.")
        for itm in order.items or []:
            if getattr(itm, "reject_reason", None):
                shipment_exc.append(f"Item #{itm.id} rejection note: {itm.reject_reason}")

        logistics_inv = LogisticsInvestigationContext(
            is_accessible=True,
            courier_company=top_courier_company,
            tracking_number=top_tracking_number,
            tracking_url=top_tracking_url,
            dispatch_date=top_dispatch_date,
            estimated_delivery=top_estimated_delivery,
            delivered_at=top_delivered_at,
            delivery_attempts=top_delivery_attempts,
            attempt_history=attempt_history,
            rider_details=rider_details_obj,
            proof_of_delivery=pod_obj,
            delivery_discrepancy=discrepancy,
            shipment_exceptions=shipment_exc
        )

    # 2. Finance Investigation
    finance_inv = None
    if "finance" in user_authorized_depts:
        wh_logs = []
        if pm:
            try:
                wh_res = await db.execute(
                    select(PaymentWebhook)
                    .where(PaymentWebhook.payment_id == pm.id)
                    .order_by(PaymentWebhook.created_at.desc())
                    .limit(10)
                )
                wh_logs = [
                    {
                        "id": w.id,
                        "event_type": w.event_type,
                        "processed": w.processed,
                        "created_at": w.created_at
                    }
                    for w in wh_res.scalars().all()
                ]
            except Exception:
                wh_logs = []

        fin_discrepancies = []
        if cod_verification_obj and cod_verification_obj.reconciliation_discrepancy:
            fin_discrepancies.append(cod_verification_obj.reconciliation_discrepancy)
        if pricing_breakdown_obj and pricing_breakdown_obj.has_pricing_discrepancy:
            fin_discrepancies.append(pricing_breakdown_obj.discrepancy_details)
        if ret and ret.status and str(ret.status).upper() in ("APPROVED", "RETURN_PICKUP_COMPLETED", "COMPLETED") and not getattr(ret, "refund_initiated", False):
            fin_discrepancies.append("Return approved/completed but refund has not been initiated.")

        refund_dict = None
        if pm and (pm.refund_amount or pm.refunded_at or pm.refund_reason):
            refund_dict = {
                "amount": float(pm.refund_amount or 0.0),
                "refund_reason": pm.refund_reason,
                "refunded_at": pm.refunded_at,
                "status": "REFUNDED" if str(pm.status).lower() == "refunded" else "PARTIAL_REFUND"
            }
        elif ret and (ret.refund_amount or ret.refund_initiated or ret.refund_reference):
            refund_dict = {
                "amount": float(ret.refund_amount or 0.0),
                "refund_mode": ret.refund_mode,
                "refund_reference": ret.refund_reference,
                "refund_initiated": ret.refund_initiated,
                "requested_at": ret.requested_at,
                "status": "INITIATED" if ret.refund_initiated else "REQUESTED"
            }

        finance_inv = FinanceInvestigationContext(
            is_accessible=True,
            payment_id=pm.id if pm else None,
            payment_method=order.payment_method,
            payment_status=pm.status.value if (pm and hasattr(pm.status, "value")) else (str(pm.status) if pm else "Pending"),
            transaction_id=pm.transaction_id if pm else None,
            payment_gateway=pm.payment_gateway if pm else None,
            amount=float(pm.amount or order.total_amount or 0.0) if pm else float(order.total_amount or 0.0),
            currency="INR",
            card_last4=getattr(pm, "card_last4", None) if pm else None,
            card_brand=getattr(pm, "card_brand", None) if pm else None,
            upi_id=getattr(pm, "upi_id", None) if pm else None,
            wallet_provider=getattr(pm, "wallet_provider", None) if pm else None,
            gateway_response_captured=bool(wh_logs),
            gateway_event_logs=wh_logs,
            pricing_breakdown=pricing_breakdown_obj,
            cod_verification=cod_verification_obj,
            refund_details=refund_dict,
            settlement_details=settlement_dict,
            financial_discrepancies=fin_discrepancies
        )

    # 3. Dealer / Product Investigation
    dealer_inv = None
    if "dealer" in user_authorized_depts:
        primary_item = None
        for itm in order.items or []:
            if ticket.order_item_id == itm.id:
                primary_item = itm
                break
        if not primary_item and order.items:
            primary_item = order.items[0]

        prod = primary_item.product if primary_item else None
        dlr = prod.dealer if prod else None
        cat = prod.category if prod else None

        fulfillment_ret = None
        if ret:
            fulfillment_ret = {
                "return_id": ret.id,
                "reason": ret.reason,
                "status": ret.status.value if hasattr(ret.status, "value") else str(ret.status),
                "is_exchange": ret.is_exchange,
                "pickup_attempts": ret.pickup_attempts,
                "images": ret.images or [],
                "admin_notes": ret.admin_notes
            }

        listing_disc = None
        if prod and primary_item:
            if prod.selling_price is not None and abs(float(prod.selling_price) - float(primary_item.price)) > 0.01:
                listing_disc = f"Catalog selling price (₹{prod.selling_price:.2f}) differs from ordered price (₹{primary_item.price:.2f})."
        if dlr and not dlr.is_approved:
            listing_disc = (listing_disc + " " if listing_disc else "") + "Dealer registration status is unapproved/pending."

        dealer_inv = DealerProductInvestigationContext(
            is_accessible=True,
            dealer_id=str(dlr.id) if dlr else None,
            dealer_name=dlr.business_name if dlr else None,
            dealer_gst=dlr.gst_number if dlr else None,
            dealer_phone=dlr.business_phone if dlr else None,
            dealer_city=dlr.city if dlr else None,
            dealer_is_approved=dlr.is_approved if dlr else None,
            product_id=str(prod.id) if prod else None,
            product_name=prod.name if prod else (primary_item.product_name if primary_item else None),
            product_sku=prod.sku if prod else None,
            category_name=cat.name if cat else None,
            hsn_code=prod.hsn_code if prod else None,
            specifications=prod.attributes if prod and prod.attributes else None,
            is_returnable=prod.is_returnable if prod else True,
            return_window_days=prod.return_window_days if prod else 14,
            return_policy_note=prod.return_policy_note if prod else None,
            item_ordered_price=float(primary_item.price) if primary_item else None,
            item_ordered_quantity=primary_item.quantity if primary_item else None,
            fulfillment_return_evidence=fulfillment_ret,
            product_images=prod.images if prod and prod.images else [],
            listing_discrepancy=listing_disc
        )

    # 4. Technology Investigation
    technology_inv = None
    if "technology" in user_authorized_depts:
        dev_info = ticket.device_info or {}
        platform_val = dev_info.get("platform") or (ticket.source.value if hasattr(ticket.source, "value") else str(ticket.source))

        integ_failures = []
        if pm and str(pm.status).lower() == "failed":
            integ_failures.append({
                "system": "Payment Gateway",
                "error": pm.failure_reason or "Transaction failed by gateway",
                "timestamp": pm.updated_at or pm.initiated_at
            })
        if ticket.complaint_reason and "Payment made still order is showing pending" in ticket.complaint_reason:
            integ_failures.append({
                "system": "Gateway Webhook Listener",
                "error": "Payment webhook notification delayed or unreceived",
                "timestamp": ticket.created_at
            })

        audit_trail = []
        try:
            audit_res = await db.execute(
                select(AuditLog)
                .where(
                    or_(
                        AuditLog.resource_id == str(order.id),
                        AuditLog.resource_id == str(ticket.id)
                    )
                )
                .order_by(AuditLog.created_at.desc())
                .limit(10)
            )
            audit_trail = [
                {
                    "action": a.action,
                    "resource_type": a.resource_type,
                    "description": a.description,
                    "ip_address": a.ip_address,
                    "timestamp": a.created_at
                }
                for a in audit_res.scalars().all()
            ]
        except Exception:
            audit_trail = []

        technology_inv = TechnologyInvestigationContext(
            is_accessible=True,
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            order_id=order.id,
            order_number=order.order_number,
            device_info=dev_info if dev_info else None,
            platform=platform_val,
            app_version=dev_info.get("app_version") or dev_info.get("version"),
            os_version=dev_info.get("os_version") or dev_info.get("os"),
            browser=dev_info.get("browser"),
            client_ip=dev_info.get("ip_address") or dev_info.get("ip"),
            ticket_source=ticket.source.value if hasattr(ticket.source, "value") else str(ticket.source),
            complaint_reason=ticket.complaint_reason,
            error_context=pm.failure_reason if (pm and pm.failure_reason) else ticket.description,
            transaction_reference=pm.transaction_id if pm else None,
            integration_failures=integ_failures,
            audit_trail=audit_trail,
            telemetry_status="Captured via client device_info and system audit trail" if (dev_info or audit_trail) else "No client device_info recorded; diagnostic logs derived from server events."
        )

    pm = order.payment
    return OrderContextResponse(
        ticket_id=ticket.id,
        order_id=order.id,
        order_number=order.order_number or f"ORD-{order.id}",
        order_status=order.status.value if hasattr(order.status, "value") else str(order.status),
        order_created_at=order.created_at,
        payment_method=order.payment_method,
        payment_status=pm.status.value if (pm and hasattr(pm.status, "value")) else (str(pm.status) if pm else "Pending"),
        payment_amount=float(pm.amount or order.total_amount or 0.0) if pm else float(order.total_amount or 0.0),
        refund_status=pm.status.value if (pm and str(pm.status).lower() == "refunded") else ("Refunded" if getattr(order, "is_refunded", False) else None),
        refund_amount=float(getattr(pm, "refund_amount", 0.0) or 0.0) if pm else 0.0,
        shipping_address=addr_dict,
        customer_id=order.customer_id,
        customer_name=cust_name,
        customer_email=cust_email,
        customer_phone=cust_phone,
        logistics_partner_name=top_logistics_name,
        courier_company=top_courier_company,
        delivery_rider_name=top_rider_name,
        delivery_rider_phone=top_rider_phone,
        delivery_status=top_delivery_status,
        tracking_number=top_tracking_number,
        tracking_url=top_tracking_url,
        dispatch_date=top_dispatch_date,
        estimated_delivery=top_estimated_delivery,
        delivered_at=top_delivered_at,
        delivery_attempts=top_delivery_attempts,
        lifecycle_timeline=lifecycle_events,
        rider_details=rider_details_obj,
        delivery_attempt_history=attempt_history,
        proof_of_delivery=pod_obj,
        pricing_breakdown=pricing_breakdown_obj,
        cod_verification=cod_verification_obj,
        return_status=return_status,
        return_reason=return_reason,
        settlement_status=settlement_status,
        settlement=settlement_dict,
        tracking=tracking_dict,
        order_items=order_items_list,
        selected_order_item=selected_item_context,
        authorized_departments=user_authorized_depts,
        active_department_view=user_authorized_depts[0] if user_authorized_depts else None,
        logistics_investigation=logistics_inv,
        finance_investigation=finance_inv,
        dealer_investigation=dealer_inv,
        technology_investigation=technology_inv
    )

@router.get("/{ticket_id}/department-investigation/{department}", response_model=DepartmentInvestigationResponse, tags=["support"])
async def get_department_investigation(
    ticket_id: int,
    department: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Backoffice: Get department-specific investigation block for authorized specialist"""
    dept_key = department.lower().strip()
    if dept_key not in ["logistics", "finance", "dealer", "technology"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid department '{department}'. Allowed departments: logistics, finance, dealer, technology"
        )

    user_depts = get_user_authorized_departments(current_user)
    if dept_key not in user_depts:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access {dept_key} department investigation details"
        )

    ctx = await get_order_context(ticket_id, current_user, db)

    if dept_key == "logistics":
        if not ctx.logistics_investigation:
            raise HTTPException(status_code=404, detail="Logistics investigation data not found for this ticket")
        return DepartmentInvestigationResponse(ticket_id=ticket_id, department=dept_key, is_accessible=True, data=ctx.logistics_investigation)
    elif dept_key == "finance":
        if not ctx.finance_investigation:
            raise HTTPException(status_code=404, detail="Finance investigation data not found for this ticket")
        return DepartmentInvestigationResponse(ticket_id=ticket_id, department=dept_key, is_accessible=True, data=ctx.finance_investigation)
    elif dept_key == "dealer":
        if not ctx.dealer_investigation:
            raise HTTPException(status_code=404, detail="Dealer investigation data not found for this ticket")
        return DepartmentInvestigationResponse(ticket_id=ticket_id, department=dept_key, is_accessible=True, data=ctx.dealer_investigation)
    elif dept_key == "technology":
        if not ctx.technology_investigation:
            raise HTTPException(status_code=404, detail="Technology investigation data not found for this ticket")
        return DepartmentInvestigationResponse(ticket_id=ticket_id, department=dept_key, is_accessible=True, data=ctx.technology_investigation)

# --- DEPARTMENT ACTION & RCA ENDPOINT ---

@router.patch("/{ticket_id}/department-action", response_model=SupportTicketResponse, tags=["support"])
async def department_action(
    ticket_id: int,
    action_in: DepartmentActionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Backoffice Specialist / Dealer Admin: Record RCA, update action, or approve exceptional refund"""
    allowed_roles = [
        UserRole.PARTNER_BACKOFFICE,
        UserRole.PARTNER_LOGISTICS_SPECIALIST,
        UserRole.PARTNER_FINANCE_SPECIALIST,
        UserRole.PARTNER_TECH_SUPPORT,
        UserRole.PARTNER_SUPPORT_MANAGER,
        UserRole.DEALER,
        UserRole.DEALER_MANAGER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to perform department actions")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    routing_roles = [
        UserRole.PARTNER_BACKOFFICE,
        UserRole.PARTNER_SUPPORT_MANAGER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
        UserRole.DEALER,
        UserRole.DEALER_MANAGER
    ]
    specialist_roles = [
        UserRole.PARTNER_FINANCE_SPECIALIST,
        UserRole.PARTNER_LOGISTICS_SPECIALIST,
        UserRole.PARTNER_TECH_SUPPORT
    ]

    current_dept = ticket.assigned_department.lower().strip() if ticket.assigned_department else None

    # Enforce department isolation for specialists
    specialist_dept = get_user_specialist_dept(current_user)
    if specialist_dept:
        if current_dept and current_dept != specialist_dept:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to perform actions on another department's tickets"
            )

    if action_in.assigned_department is not None:
        new_dept = action_in.assigned_department.lower().strip()
        if new_dept not in VALID_DEPARTMENTS:
            raise HTTPException(status_code=400, detail=f"Invalid department. Allowed: {VALID_DEPARTMENTS}")
        
        # If new_dept is different from current_dept and user is a specialist, reject!
        if current_dept and new_dept != current_dept and current_user.role in specialist_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Specialists are not authorized to change the assigned department from '{current_dept}' to '{new_dept}'"
            )
        
        if current_user.role in routing_roles or not current_dept or new_dept == current_dept:
            ticket.assigned_department = new_dept
    
    dept = ticket.assigned_department or "specialist"
    if action_in.root_cause_analysis is not None:
        ticket.root_cause_analysis = action_in.root_cause_analysis
    if action_in.action_taken is not None:
        ticket.action_taken = action_in.action_taken
    if action_in.exceptional_refund_approved is not None:
        # Only finance, dealer, or admin can approve exceptional refund
        if current_user.role not in [UserRole.PARTNER_FINANCE_SPECIALIST, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.DEALER, UserRole.DEALER_MANAGER]:
            raise HTTPException(status_code=403, detail="Only Finance Specialist, Dealer, or Admin can authorize exceptional refund")
        ticket.exceptional_refund_approved = action_in.exceptional_refund_approved

    # Internal Audit message
    audit_text = f"[Department Action - {dept.upper()}] by {current_user.full_name or current_user.email}:\n"
    if action_in.root_cause_analysis:
        audit_text += f"RCA: {action_in.root_cause_analysis}\n"
    if action_in.action_taken:
        audit_text += f"Action: {action_in.action_taken}\n"
    if action_in.offline_refund_reference:
        audit_text += f"Offline Refund Ref: {action_in.offline_refund_reference} (Amount: ₹{action_in.offline_refund_amount or 0.0})\n"
    if action_in.exceptional_refund_approved:
        audit_text += f"Exceptional Refund: APPROVED\n"

    new_msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=audit_text.strip(),
        is_internal_note=True
    )
    db.add(new_msg)
    await db.commit()

    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

# --- GET MY TICKETS ---

@router.get("/my-tickets", response_model=List[CustomerSupportTicketResponse], tags=["support"])
async def get_my_tickets(
    skip: int = 0, limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Customer: Get their tickets"""
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.customer_id == current_user.id)
        .order_by(SupportTicket.created_at.desc())
        .offset(skip).limit(limit)
    )
    tickets = res.scalars().all()
    return [serialize_customer_ticket(t) for t in tickets]

@router.get("/{ticket_id}", response_model=Union[CustomerSupportTicketResponse, SupportTicketResponse], tags=["support"])
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """View full ticket (accessible by customer involved or backoffice/helpdesk)"""
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    is_cust = (current_user.role == "customer" or current_user.role == UserRole.CUSTOMER or getattr(current_user, "is_customer", False))
    if is_cust and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")
        
    if is_cust:
        return serialize_customer_ticket(ticket)
        
    specialist_dept = get_user_specialist_dept(current_user)
    if specialist_dept:
        current_dept = ticket.assigned_department.lower().strip() if ticket.assigned_department else None
        if current_dept and current_dept != specialist_dept:
            raise HTTPException(status_code=403, detail="Not authorized to view another department's tickets")

    return ticket

@router.post("/{ticket_id}/messages", response_model=TicketMessageResponse, tags=["support"])
async def add_message(
    ticket_id: int,
    msg_in: TicketMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a reply or internal note to a ticket"""
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Cannot reply to a closed ticket")
        
    if current_user.role == "customer":
        if ticket.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your ticket")
        msg_in.is_internal_note = False
        if ticket.status == TicketStatus.WAITING_ON_CUSTOMER:
            ticket.status = TicketStatus.IN_PROGRESS

    specialist_dept = get_user_specialist_dept(current_user)
    is_backoffice_role = current_user.role in [
        UserRole.PARTNER_BACKOFFICE,
        UserRole.PARTNER_LOGISTICS_SPECIALIST,
        UserRole.PARTNER_FINANCE_SPECIALIST,
        UserRole.PARTNER_TECH_SUPPORT
    ] or bool(specialist_dept)

    # Backoffice personnel can only add internal notes while ticket is in Backoffice stage
    if is_backoffice_role and ticket.ticket_stage == TicketStage.BACKOFFICE and not msg_in.is_internal_note:
        raise HTTPException(
            status_code=403,
            detail="Backoffice specialists cannot send public customer replies while ticket is in Backoffice stage. Customer replies are restricted to Helpdesk."
        )
            
    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=msg_in.message,
        is_internal_note=msg_in.is_internal_note or False,
        attachment_url=msg_in.attachment_url
    )
    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)
    return new_message

@router.patch("/{ticket_id}/status", response_model=Union[CustomerSupportTicketResponse, SupportTicketResponse], tags=["support"])
async def update_status(
    ticket_id: int,
    status_in: TicketStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change ticket status"""
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    is_cust = (current_user.role == "customer" or current_user.role == UserRole.CUSTOMER or getattr(current_user, "is_customer", False))
    if is_cust and status_in.status != TicketStatus.CLOSED:
        raise HTTPException(status_code=403, detail="Customers can only close tickets")

    # Enforce hierarchy: Backoffice cannot resolve/close tickets directly; must return to Helpdesk
    if status_in.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
        if ticket.ticket_stage == TicketStage.BACKOFFICE and current_user.role not in [
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN,
            UserRole.PARTNER_SUPPORT_MANAGER
        ]:
            raise HTTPException(
                status_code=403,
                detail="Backoffice specialists cannot resolve or close tickets directly. Please use 'Return to Helpdesk' to submit investigation findings."
            )
        
    ticket.status = status_in.status
    if status_in.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
        ticket.resolved_at = datetime.utcnow()
        if not is_cust:
            ticket.resolved_by_user_id = current_user.id
    elif status_in.status in [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_ON_CUSTOMER]:
        ticket.resolved_at = None
        ticket.resolved_by_user_id = None
        
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    updated_ticket = res.scalar_one()
    if is_cust:
        return serialize_customer_ticket(updated_ticket)
    return updated_ticket

# --- ESCALATION & ROUTING ENDPOINTS ---

@router.post("/{ticket_id}/escalate-to-backoffice", response_model=SupportTicketResponse, tags=["support"])
async def escalate_to_backoffice(
    ticket_id: int,
    escalate_in: TicketEscalateCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Helpdesk: Escalate ticket to BACKOFFICE stage"""
    allowed_roles = [
        UserRole.PARTNER_HELPDESK_OPERATOR,
        UserRole.PARTNER_HELPDESK_SUPERVISOR,
        UserRole.PARTNER_HELPDESK_MANAGER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to escalate tickets")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    ticket.ticket_stage = TicketStage.BACKOFFICE
    ticket.assigned_user_id = None
    if escalate_in.target_department:
        ticket.assigned_department = escalate_in.target_department.lower().strip()
    if escalate_in.reason:
        ticket.escalation_reason = escalate_in.reason
    if escalate_in.investigation_request:
        ticket.investigation_request = escalate_in.investigation_request
    
    req_suffix = f" | Request: {escalate_in.investigation_request}" if escalate_in.investigation_request else ""
    escalate_msg = f"[Escalated to Backoffice] Reason: {escalate_in.reason or 'General'}{req_suffix}"
    if escalate_in.target_department:
        escalate_msg += f" (Assigned Dept: {escalate_in.target_department.upper()})"

    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=escalate_msg,
        is_internal_note=True
    )
    db.add(new_message)
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

@router.post("/{ticket_id}/return-to-helpdesk", response_model=SupportTicketResponse, tags=["support"])
async def return_to_helpdesk(
    ticket_id: int,
    return_in: TicketReturnCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Backoffice: Return ticket to HELPDESK stage with resolution summary"""
    allowed_roles = [
        UserRole.PARTNER_BACKOFFICE,
        UserRole.PARTNER_LOGISTICS_SPECIALIST,
        UserRole.PARTNER_FINANCE_SPECIALIST,
        UserRole.PARTNER_TECH_SUPPORT,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to return tickets to Helpdesk")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    specialist_dept = get_user_specialist_dept(current_user)
    if specialist_dept:
        current_dept = ticket.assigned_department.lower().strip() if ticket.assigned_department else None
        if current_dept and current_dept != specialist_dept:
            raise HTTPException(status_code=403, detail="Not authorized to return another department's tickets")
        
    ticket.ticket_stage = TicketStage.HELPDESK

    # Locate originating helpdesk operator from the latest escalation audit log
    esc_msg_res = await db.execute(
        select(TicketMessage)
        .where(
            TicketMessage.ticket_id == ticket.id,
            TicketMessage.is_internal_note == True,
            TicketMessage.message.like("[Escalated to Backoffice]%")
        )
        .order_by(TicketMessage.created_at.desc())
    )
    latest_esc_msg = esc_msg_res.scalars().first()
    assigned_helpdesk_operator_id = None
    if isinstance(latest_esc_msg, TicketMessage) and latest_esc_msg.sender_id:
        u_res = await db.execute(
            select(User).where(User.id == latest_esc_msg.sender_id, User.is_active == True)
        )
        originating_user = u_res.scalar_one_or_none()
        valid_helpdesk_roles = [
            UserRole.PARTNER_HELPDESK_OPERATOR,
            UserRole.PARTNER_HELPDESK_SUPERVISOR,
            UserRole.PARTNER_HELPDESK_MANAGER,
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN
        ]
        if originating_user and isinstance(originating_user, User) and originating_user.role in valid_helpdesk_roles:
            assigned_helpdesk_operator_id = originating_user.id

    ticket.assigned_user_id = assigned_helpdesk_operator_id

    routing_suffix = f" (Reassigned to Helpdesk Operator #{assigned_helpdesk_operator_id})" if assigned_helpdesk_operator_id else " (Unassigned in Helpdesk queue)"
    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=f"[Returned to Helpdesk] Resolution Summary: {return_in.resolution_summary}{routing_suffix}",
        is_internal_note=True
    )
    db.add(new_message)
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

@router.post("/{ticket_id}/claim", response_model=SupportTicketResponse, tags=["support"])
async def claim_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Backoffice Specialist: Claim an unassigned ticket in BACKOFFICE stage"""
    allowed_roles = [
        UserRole.PARTNER_BACKOFFICE,
        UserRole.PARTNER_LOGISTICS_SPECIALIST,
        UserRole.PARTNER_FINANCE_SPECIALIST,
        UserRole.PARTNER_TECH_SUPPORT,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to claim Backoffice tickets")

    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.ticket_stage != TicketStage.BACKOFFICE:
        raise HTTPException(status_code=400, detail="Only tickets in Backoffice stage can be claimed by Backoffice specialists")

    specialist_dept = get_user_specialist_dept(current_user)
    if specialist_dept:
        ticket_dept = ticket.assigned_department.lower().strip() if ticket.assigned_department else None
        if ticket_dept and ticket_dept != specialist_dept:
            raise HTTPException(status_code=403, detail="Cannot claim a ticket assigned to another department")

    if ticket.assigned_user_id is not None:
        if ticket.assigned_user_id != current_user.id:
            raise HTTPException(status_code=409, detail="Ticket is already claimed by another specialist")
    else:
        ticket.assigned_user_id = current_user.id
        dept_name = (ticket.assigned_department or "Backoffice").capitalize()
        claim_msg = TicketMessage(
            ticket_id=ticket.id,
            sender_id=current_user.id,
            message=f"[Ticket Claimed] Claimed by {current_user.full_name or current_user.email} ({dept_name})",
            is_internal_note=True
        )
        db.add(claim_msg)
        await db.commit()

    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

@router.patch("/{ticket_id}/assign", response_model=SupportTicketResponse, tags=["support"])
async def assign_ticket(
    ticket_id: int,
    assign_in: TicketAssignUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign ticket to a specific operator/specialist"""
    allowed_roles = [
        UserRole.PARTNER_HELPDESK_SUPERVISOR,
        UserRole.PARTNER_HELPDESK_MANAGER,
        UserRole.PARTNER_BACKOFFICE,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to assign tickets")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if assign_in.assigned_user_id is not None:
        u_res = await db.execute(select(User).where(User.id == assign_in.assigned_user_id, User.is_active == True))
        target_user = u_res.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target assignee user not found or inactive")
        
        valid_assignee_roles = [
            UserRole.PARTNER_HELPDESK_OPERATOR,
            UserRole.PARTNER_HELPDESK_SUPERVISOR,
            UserRole.PARTNER_HELPDESK_MANAGER,
            UserRole.PARTNER_BACKOFFICE,
            UserRole.PARTNER_LOGISTICS_SPECIALIST,
            UserRole.PARTNER_FINANCE_SPECIALIST,
            UserRole.PARTNER_TECH_SUPPORT,
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN
        ]
        if target_user.role not in valid_assignee_roles:
            raise HTTPException(status_code=400, detail="Cannot assign ticket to non-support user")
        
    ticket.assigned_user_id = assign_in.assigned_user_id
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

@router.post("/{ticket_id}/feedback", response_model=CustomerSupportTicketResponse, tags=["support"])
async def provide_feedback(
    ticket_id: int,
    feedback_in: TicketFeedbackCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Customer: Provide 1-5 star feedback for a closed ticket"""
    if current_user.role != "customer" and getattr(current_user, "is_customer", False) is False and getattr(current_user, "role", "") != UserRole.CUSTOMER:
        raise HTTPException(status_code=403, detail="Only customers can provide feedback")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket or ticket.customer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if ticket.status != TicketStatus.CLOSED and ticket.status != TicketStatus.RESOLVED:
        raise HTTPException(status_code=400, detail="Ticket must be resolved/closed to provide feedback")
        
    ticket.customer_feedback_rating = max(1, min(5, feedback_in.rating))
    ticket.customer_feedback_comments = feedback_in.comments
    ticket.status = TicketStatus.CLOSED
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user),
            selectinload(SupportTicket.resolved_by_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return serialize_customer_ticket(res.scalar_one())

@router.get("/partner/all", response_model=List[SupportTicketResponse], tags=["support"])
async def partner_queue(
    stage: Optional[TicketStage] = None,
    department: Optional[str] = None,
    assigned_to_me: bool = False,
    is_history: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for Partner Helpdesk & Backoffice queues with department filtering"""
    allowed_roles = [
        UserRole.PARTNER_HELPDESK_OPERATOR,
        UserRole.PARTNER_HELPDESK_SUPERVISOR,
        UserRole.PARTNER_HELPDESK_MANAGER,
        UserRole.PARTNER_BACKOFFICE,
        UserRole.PARTNER_LOGISTICS_SPECIALIST,
        UserRole.PARTNER_FINANCE_SPECIALIST,
        UserRole.PARTNER_TECH_SUPPORT,
        UserRole.PARTNER_SUPPORT_MANAGER,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    query = select(SupportTicket).options(
        selectinload(SupportTicket.messages),
        selectinload(SupportTicket.assigned_user),
        selectinload(SupportTicket.resolved_by_user)
    )
    
    if stage:
        if is_history and stage == TicketStage.HELPDESK:
            # Helpdesk History encompasses all completed tickets handled by Helpdesk (including those escalated to Backoffice)
            pass
        else:
            query = query.where(SupportTicket.ticket_stage == stage)

    specialist_dept = get_user_specialist_dept(current_user)
    if specialist_dept:
        query = query.where(SupportTicket.assigned_department == specialist_dept)
    elif department and department.upper() != "ALL":
        query = query.where(SupportTicket.assigned_department == department.lower())

    if current_user.role == UserRole.PARTNER_HELPDESK_OPERATOR:
        if is_history:
            query = query.where(
                or_(
                    SupportTicket.assigned_user_id == current_user.id,
                    SupportTicket.id.in_(
                        select(TicketMessage.ticket_id).where(TicketMessage.sender_id == current_user.id)
                    )
                )
            )
        elif assigned_to_me:
            query = query.where(SupportTicket.assigned_user_id == current_user.id)
    elif assigned_to_me:
        query = query.where(SupportTicket.assigned_user_id == current_user.id)

    if is_history:
        query = query.where(SupportTicket.status.in_([TicketStatus.RESOLVED, TicketStatus.CLOSED]))
    else:
        query = query.where(SupportTicket.status != TicketStatus.CLOSED)
        
    query = query.order_by(SupportTicket.created_at.desc())
    res = await db.execute(query)
    return res.scalars().all()

@router.get("/partner/operators", tags=["support"])
async def get_operators(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch active Helpdesk operators and Backoffice specialists for assignment"""
    res = await db.execute(
        select(User.id, User.email, User.full_name, User.role)
        .where(
            User.role.in_([
                UserRole.PARTNER_HELPDESK_OPERATOR,
                UserRole.PARTNER_HELPDESK_SUPERVISOR,
                UserRole.PARTNER_BACKOFFICE,
                UserRole.PARTNER_LOGISTICS_SPECIALIST,
                UserRole.PARTNER_FINANCE_SPECIALIST,
                UserRole.PARTNER_TECH_SUPPORT
            ]),
            User.is_active == True
        )
    )
    users = res.all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role} for u in users]

@router.patch("/partner/bulk-assign", tags=["support"])
async def bulk_assign_tickets(
    bulk_assign_in: TicketBulkAssign,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Bulk assign tickets to a specific user"""
    allowed_roles = [
        UserRole.PARTNER_HELPDESK_SUPERVISOR,
        UserRole.PARTNER_HELPDESK_MANAGER,
        UserRole.PARTNER_BACKOFFICE,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN
    ]
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to bulk assign tickets")
        
    if not bulk_assign_in.ticket_ids:
        return {"message": "No tickets provided", "updated_count": 0}

    if bulk_assign_in.assigned_user_id is not None:
        u_res = await db.execute(select(User).where(User.id == bulk_assign_in.assigned_user_id, User.is_active == True))
        target_user = u_res.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target assignee user not found or inactive")
        
        valid_assignee_roles = [
            UserRole.PARTNER_HELPDESK_OPERATOR,
            UserRole.PARTNER_HELPDESK_SUPERVISOR,
            UserRole.PARTNER_HELPDESK_MANAGER,
            UserRole.PARTNER_BACKOFFICE,
            UserRole.PARTNER_LOGISTICS_SPECIALIST,
            UserRole.PARTNER_FINANCE_SPECIALIST,
            UserRole.PARTNER_TECH_SUPPORT,
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN
        ]
        if target_user.role not in valid_assignee_roles:
            raise HTTPException(status_code=400, detail="Cannot assign ticket to non-support user")
        
    res = await db.execute(
        select(SupportTicket).where(SupportTicket.id.in_(bulk_assign_in.ticket_ids))
    )
    tickets = res.scalars().all()
    
    updated_count = 0
    for ticket in tickets:
        if ticket.status == TicketStatus.CLOSED:
            raise HTTPException(status_code=400, detail=f"Validation Error: Cannot reassign closed ticket #{ticket.ticket_number}.")
        ticket.assigned_user_id = bulk_assign_in.assigned_user_id
        updated_count += 1
        
    await db.commit()
    return {"message": "Tickets successfully assigned", "updated_count": updated_count}
