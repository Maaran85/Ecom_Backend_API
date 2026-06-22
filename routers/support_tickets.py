from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import string
import random

from core.database import get_db
from models.user import User, UserRole
from models.support_ticket import SupportTicket, TicketMessage, TicketStatus, TicketStage, TicketSLAStatus
from models.cart import OrderItem, Order
from models.dealer import Dealer
from schemas.support_ticket import (
    SupportTicketCreate, SupportTicketResponse, 
    TicketMessageCreate, TicketMessageResponse,
    TicketStatusUpdate, TicketAssignUpdate, TicketFeedbackCreate, TicketBulkAssign,
    TicketEscalateCreate, TicketReturnCreate
)
from core.permissions import get_current_active_user, require_admin

router = APIRouter()

def generate_ticket_number():
    chars = string.ascii_uppercase + string.digits
    return "TKT-" + ''.join(random.choices(chars, k=6))

# --- CUSTOMER ENDPOINTS ---

@router.post("/", response_model=SupportTicketResponse, tags=["support"])
async def create_ticket(
    ticket_in: SupportTicketCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Customer: Create a support ticket"""
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can create tickets")
        
    dealer_id = None
    partner_id = None
    order_id = None
    product_id = None
    
    if ticket_in.order_item_id:
        res = await db.execute(
            select(OrderItem, Order)
            .join(Order, OrderItem.order_id == Order.id)
            .where(OrderItem.id == ticket_in.order_item_id, Order.user_id == current_user.id)
        )
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Order item not found or does not belong to you")
        
        order_item, order = row
        order_id = order.id
        dealer_id = order_item.dealer_id
        product_id = order_item.product_id
        
        if dealer_id:
            dealer_res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
            dealer = dealer_res.scalar_one_or_none()
            if dealer:
                partner_id = dealer.partner_id

    now = datetime.now(timezone.utc)
    escalation_deadline = now + timedelta(hours=4) # 4 hours SLA for first response
    
    assigned_user_id = None
    
    # Auto-Assign logic: find PARTNER_HELPDESK_OPERATOR user with least open tickets
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
        product_id=product_id,
        subject=ticket_in.subject,
        description=ticket_in.description,
        ticket_type=ticket_in.ticket_type,
        source=ticket_in.source,
        ticket_stage=TicketStage.HELPDESK,
        assigned_user_id=assigned_user_id,
        escalation_deadline=escalation_deadline,
        attachments=ticket_in.attachments
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
    return res.scalar_one()

@router.get("/my-tickets", response_model=List[SupportTicketResponse], tags=["support"])
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
            selectinload(SupportTicket.assigned_user)
        )
        .where(SupportTicket.customer_id == current_user.id)
        .order_by(SupportTicket.created_at.desc())
        .offset(skip).limit(limit)
    )
    return res.scalars().all()

@router.get("/{ticket_id}", response_model=SupportTicketResponse, tags=["support"])
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """View full ticket (accessible by anyone involved)"""
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    # Check permissions
    if current_user.role == "customer" and ticket.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your ticket")
        
    # Hide internal notes from customer
    if current_user.role == "customer":
        ticket.messages = [m for m in ticket.messages if not m.is_internal_note]
        
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
            
    if current_user.role == UserRole.PARTNER_HELPDESK_OPERATOR and ticket.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only reply to tickets assigned to you")
            
    # Add message
    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=msg_in.message,
        is_internal_note=msg_in.is_internal_note,
        attachment_url=msg_in.attachment_url
    )
    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)
    return new_message

@router.patch("/{ticket_id}/status", response_model=SupportTicketResponse, tags=["support"])
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
        
    if current_user.role == "customer" and status_in.status != TicketStatus.CLOSED:
        raise HTTPException(status_code=403, detail="Customers can only CLOSE tickets")
        
    if current_user.role == UserRole.PARTNER_HELPDESK_OPERATOR and ticket.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only update tickets assigned to you")
            
    ticket.status = status_in.status
    if status_in.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
        ticket.resolved_at = datetime.utcnow()
        
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

# --- PARTNER / ADMIN ENDPOINTS ---

@router.post("/{ticket_id}/escalate-to-backoffice", response_model=SupportTicketResponse, tags=["support"])
async def escalate_to_backoffice(
    ticket_id: int,
    escalate_in: TicketEscalateCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Helpdesk: Escalate ticket to BACKOFFICE stage"""
    if current_user.role not in [UserRole.PARTNER_HELPDESK_OPERATOR, UserRole.PARTNER_HELPDESK_SUPERVISOR, UserRole.PARTNER_HELPDESK_MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if current_user.role == UserRole.PARTNER_HELPDESK_OPERATOR:
        if ticket.assigned_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only escalate tickets assigned to you")
            
    ticket.ticket_stage = TicketStage.BACKOFFICE
    ticket.assigned_user_id = None
    
    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=escalate_in.reason,
        is_internal_note=True
    )
    db.add(new_message)
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
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
    """Backoffice: Return ticket to HELPDESK stage"""
    if current_user.role not in [UserRole.PARTNER_BACKOFFICE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    ticket.ticket_stage = TicketStage.HELPDESK
    ticket.assigned_user_id = None
    
    new_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_user.id,
        message=return_in.resolution_summary,
        is_internal_note=True
    )
    db.add(new_message)
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
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
    """Assign ticket to a specific user"""
    if current_user.role not in [UserRole.PARTNER_HELPDESK_SUPERVISOR, UserRole.PARTNER_HELPDESK_MANAGER, UserRole.PARTNER_BACKOFFICE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized to assign tickets")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    ticket.assigned_user_id = assign_in.assigned_user_id
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

@router.post("/{ticket_id}/feedback", response_model=SupportTicketResponse, tags=["support"])
async def provide_feedback(
    ticket_id: int,
    feedback_in: TicketFeedbackCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Customer: Provide feedback for a closed ticket"""
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can provide feedback")
        
    res = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = res.scalar_one_or_none()
    if not ticket or ticket.customer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if ticket.status != TicketStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Ticket must be closed to provide feedback")
        
    ticket.customer_feedback_rating = feedback_in.rating
    ticket.customer_feedback_comments = feedback_in.comments
    await db.commit()
    
    res = await db.execute(
        select(SupportTicket)
        .options(
            selectinload(SupportTicket.messages),
            selectinload(SupportTicket.assigned_user)
        )
        .where(SupportTicket.id == ticket_id)
    )
    return res.scalar_one()

@router.get("/partner/all", response_model=List[SupportTicketResponse], tags=["support"])
async def partner_queue(
    stage: Optional[TicketStage] = None,
    assigned_to_me: bool = False,
    is_history: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get tickets for Partner queues"""
    if current_user.role not in [UserRole.PARTNER_HELPDESK_OPERATOR, UserRole.PARTNER_HELPDESK_SUPERVISOR, UserRole.PARTNER_HELPDESK_MANAGER, UserRole.PARTNER_BACKOFFICE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    query = select(SupportTicket).options(
        selectinload(SupportTicket.messages),
        selectinload(SupportTicket.assigned_user)
    )
    
    if stage:
        query = query.where(SupportTicket.ticket_stage == stage)
    if assigned_to_me:
        query = query.where(SupportTicket.assigned_user_id == current_user.id)

    if is_history:
        query = query.where(SupportTicket.status == TicketStatus.CLOSED)
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
    """Fetch all active helpdesk operators"""
    if current_user.role not in [UserRole.PARTNER_HELPDESK_SUPERVISOR, UserRole.PARTNER_HELPDESK_MANAGER, UserRole.PARTNER_BACKOFFICE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    res = await db.execute(
        select(User.id, User.email, User.full_name)
        .where(
            User.role == UserRole.PARTNER_HELPDESK_OPERATOR,
            User.is_active == True
        )
    )
    users = res.all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name} for u in users]

@router.patch("/partner/bulk-assign", tags=["support"])
async def bulk_assign_tickets(
    bulk_assign_in: TicketBulkAssign,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Bulk assign tickets to a specific user"""
    if current_user.role not in [UserRole.PARTNER_HELPDESK_SUPERVISOR, UserRole.PARTNER_HELPDESK_MANAGER, UserRole.PARTNER_BACKOFFICE, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized to bulk assign tickets")
        
    if not bulk_assign_in.ticket_ids:
        return {"message": "No tickets provided", "updated_count": 0}
        
    res = await db.execute(
        select(SupportTicket).where(SupportTicket.id.in_(bulk_assign_in.ticket_ids))
    )
    tickets = res.scalars().all()
    
    updated_count = 0
    for ticket in tickets:
        if ticket.status == "CLOSED":
            raise HTTPException(status_code=400, detail=f"Validation Error: Cannot reassign closed ticket #{ticket.ticket_number}.")
        ticket.assigned_user_id = bulk_assign_in.assigned_user_id
        updated_count += 1
        
    await db.commit()
    
    return {"message": "Tickets successfully assigned", "updated_count": updated_count}
