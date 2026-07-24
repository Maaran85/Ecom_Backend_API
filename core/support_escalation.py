import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, update
import logging

from core.database import SessionLocal
from models.support_ticket import SupportTicket, TicketSLAStatus, TicketStatus

logger = logging.getLogger(__name__)

async def escalate_overdue_tickets():
    """
    Background task to check for support tickets that have breached their SLA.
    Marks them as BREACHED.
    """
    try:
        async with SessionLocal() as db:
            now = datetime.utcnow()
            
            # Find all tickets currently open/in-progress that are past deadline
            query = select(SupportTicket).where(
                SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
                SupportTicket.sla_status == TicketSLAStatus.ON_TRACK,
                SupportTicket.escalation_deadline <= now
            )
            
            result = await db.execute(query)
            overdue_tickets = result.scalars().all()
            
            if overdue_tickets:
                logger.info(f"Marking {len(overdue_tickets)} support tickets as SLA BREACHED.")
                
                # Update them
                for ticket in overdue_tickets:
                    ticket.sla_status = TicketSLAStatus.BREACHED
                    ticket.updated_at = now
                
                await db.commit()
    except Exception as e:
        logger.error(f"Error in escalate_overdue_tickets: {e}")

async def start_support_escalation_loop():
    """Runs continuously in the background."""
    logger.info("Starting support escalation background loop...")
    while True:
        await escalate_overdue_tickets()
        # Run every 5 minutes (300 seconds)
        await asyncio.sleep(300)
