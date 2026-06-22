import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from core.database import SessionLocal, engine
from models.support_ticket import SupportTicket, TicketMessage
from sqlalchemy import text

async def alter_tables():
    async with engine.begin() as conn:
        # Check if support_tickets exists
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'support_tickets';"))
        existing_columns = [r[0] for r in res.fetchall()]
        
        if existing_columns:
            # Add missing columns safely
            queries = [
                ("partner_id", "ALTER TABLE support_tickets ADD COLUMN partner_id INTEGER REFERENCES partners(id)"),
                ("priority", "ALTER TABLE support_tickets ADD COLUMN priority VARCHAR DEFAULT 'medium'"),
                ("current_level", "ALTER TABLE support_tickets ADD COLUMN current_level VARCHAR DEFAULT 'dealer'"),
                ("escalation_deadline", "ALTER TABLE support_tickets ADD COLUMN escalation_deadline TIMESTAMP WITH TIME ZONE"),
                ("is_handled_by_dealer", "ALTER TABLE support_tickets ADD COLUMN is_handled_by_dealer BOOLEAN DEFAULT FALSE"),
                ("resolved_at", "ALTER TABLE support_tickets ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE"),
                ("ticket_number", "ALTER TABLE support_tickets ADD COLUMN ticket_number VARCHAR(50)")
            ]
            for col, query in queries:
                if col not in existing_columns:
                    try:
                        await conn.execute(text(query))
                        print(f"Added column {col} to support_tickets")
                    except Exception as e:
                        print(f"Failed to add {col}: {e}")
        else:
            # Create support_tickets table if it doesn't exist
            from core.database import Base
            await conn.run_sync(Base.metadata.create_all)
            print("Created tables")

        # Create ticket_messages if it doesn't exist
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ticket_messages';"))
        if not res.fetchall():
            from core.database import Base
            await conn.run_sync(Base.metadata.create_all)
            print("Created ticket_messages table")
        else:
            print("ticket_messages table already exists")

if __name__ == "__main__":
    asyncio.run(alter_tables())
