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
from models.product import Product
from models.payment import Payment
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
                    (CustomerUser.email == ident) | (CustomerUser.phone_number == ident)
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
        if order and order.items:
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
        
    if not ticket.order_id and not ticket.order_item_id:
        return OrderContextResponse(ticket_id=ticket.id)
        
    order = None
    if ticket.order_id:
        order_res = await db.execute(
            select(Order)
            .where(Order.id == ticket.order_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
                selectinload(Order.payment),
                selectinload(Order.shipping_address).selectinload(Address.state_rel)
            )
        )
        order = order_res.scalar_one_or_none()
    elif ticket.order_item_id:
        item_res = await db.execute(
            select(OrderItem)
            .where(OrderItem.id == ticket.order_item_id)
            .options(
                selectinload(OrderItem.order).selectinload(Order.payment),
                selectinload(OrderItem.order).selectinload(Order.shipping_address).selectinload(Address.state_rel),
                selectinload(OrderItem.product).selectinload(Product.dealer)
            )
        )
        found_item = item_res.scalar_one_or_none()
        if found_item:
            order = found_item.order

    if not order:
        return OrderContextResponse(ticket_id=ticket.id, order_id=ticket.order_id)

    # Shipping Address dict
    addr_dict = None
    if order.shipping_address:
        addr = order.shipping_address
        addr_dict = {
            "address_line1": getattr(addr, "address_line1", None) or getattr(addr, "address", None),
            "city": getattr(addr, "city", None),
            "state": (
                getattr(getattr(addr, "state_rel", None), "name", None)
                or (str(getattr(addr, "state_id", "")) if getattr(addr, "state_id", None) else None)
            ),
            "pincode": getattr(addr, "pincode", None),
        }

    # Logistics & Rider Info
    logistics_name = None
    rider_name = None
    rider_phone = None
    delivery_status = order.status.value if hasattr(order.status, "value") else str(order.status)

    # Items breakdown
    order_items_list = []
    selected_item_context = None

    settlement_config = await get_settlement_configuration(db)

    for itm in order.items:
        prod = itm.product
        dealer = prod.dealer if prod else None
        
        # Calculate protection maturity
        mat_dt = None
        deliv = itm.delivered_at or order.delivered_at
        if deliv:
            win = get_effective_protection_window(itm, product=prod, global_config=settlement_config)
            mat_dt = deliv + timedelta(days=win)
            
        item_ctx = OrderItemContext(
            id=itm.id,
            product_id=itm.product_id,
            product_name=prod.name if prod else "Unknown Product",
            product_image=(prod.images[0] if (prod and getattr(prod, 'images', None) and isinstance(prod.images, list) and len(prod.images) > 0) else getattr(prod, 'image_url', None)),
            quantity=itm.quantity or 1,
            price=float(itm.price or 0.0),
            status=itm.status.value if hasattr(itm.status, 'value') else (str(itm.status) if itm.status is not None else None),
            delivered_at=deliv,
            return_window_matures_at=mat_dt,
            dealer_name=dealer.business_name if dealer else None,
            dealer_id=dealer.id if dealer else None
        )
        order_items_list.append(item_ctx)
        if ticket.order_item_id == itm.id:
            selected_item_context = item_ctx
            
        # Check logistics info from item
        lp_id = getattr(itm, "logistics_partner_id", None)
        if lp_id and not logistics_name:
            lp_res = await db.execute(select(LogisticsPartner).where(LogisticsPartner.id == lp_id))
            lp = lp_res.scalar_one_or_none()
            if lp: logistics_name = lp.name
            
        r_id = getattr(itm, "rider_id", None) or getattr(itm, "delivery_rider_id", None)
        if r_id and not rider_name:
            r_res = await db.execute(select(DeliveryRider).where(DeliveryRider.id == r_id))
            rd = r_res.scalar_one_or_none()
            if rd:
                rider_name = rd.full_name
                rider_phone = rd.phone_number

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

    # Settlement status
    settlement_status = "Not generated"
    settle_item_res = await db.execute(
        select(SettlementItem, Settlement)
        .join(Settlement, SettlementItem.settlement_id == Settlement.id)
        .where(SettlementItem.order_id == order.id)
    )
    si_row = settle_item_res.first()
    if si_row:
        si, st = si_row
        settlement_status = f"{st.status.value.upper()} (Settlement #{st.settlement_number or st.id})"

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
        logistics_partner_name=logistics_name,
        delivery_rider_name=rider_name,
        delivery_rider_phone=rider_phone,
        delivery_status=delivery_status,
        return_status=return_status,
        return_reason=return_reason,
        settlement_status=settlement_status,
        order_items=order_items_list,
        selected_order_item=selected_item_context
    )

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
    ticket.assigned_user_id = None
    
    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=f"[Returned to Helpdesk] Resolution Summary: {return_in.resolution_summary}",
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
