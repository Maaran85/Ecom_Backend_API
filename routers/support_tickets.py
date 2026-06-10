"""
Support tickets router (Queries & Complaints)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.database import get_db
from core.permissions import get_current_active_user
from models.user import User
from models.customer_user import CustomerUser
from models.dealer import Dealer
from models.support_ticket import SupportTicket, TicketStatus
from schemas.support_ticket import SupportTicketCreate, SupportTicketUpdate, SupportTicketResponse

router = APIRouter()

@router.post("/", response_model=SupportTicketResponse, tags=["support"])
async def create_ticket(
    ticket: SupportTicketCreate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    new_ticket = SupportTicket(
        **ticket.model_dump(),
        customer_id=current_user.id
    )
    db.add(new_ticket)
    await db.commit()
    await db.refresh(new_ticket)
    return new_ticket

@router.get("/my-tickets", response_model=List[SupportTicketResponse], tags=["support"])
async def get_my_tickets(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(SupportTicket).where(SupportTicket.customer_id == current_user.id)
    )
    return result.scalars().all()

@router.get("/dealer-tickets", response_model=List[SupportTicketResponse], tags=["support"])
async def get_dealer_tickets(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Resolve dealer ID
    dealer_id = None
    if current_user.dealer_id:
        dealer_id = current_user.dealer_id
    else:
        # Check if user IS the primary dealer user
        res = await db.execute(select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = res.scalar_one_or_none()
        if dealer:
            dealer_id = dealer.id

    if not dealer_id:
         # If no dealer identity found, return empty list
         return []

    # 2. Fetch tickets for this dealer
    result = await db.execute(
        select(SupportTicket).where(SupportTicket.dealer_id == dealer_id)
    )
    return result.scalars().all()

@router.put("/{ticket_id}", response_model=SupportTicketResponse, tags=["support"])
async def update_ticket_status(
    ticket_id: int,
    ticket_update: SupportTicketUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket_update.status:
        ticket.status = ticket_update.status

    await db.commit()
    await db.refresh(ticket)
    return ticket
