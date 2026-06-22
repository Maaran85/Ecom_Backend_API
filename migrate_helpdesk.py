import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from core.database import SessionLocal, engine
from sqlalchemy import text
from models.knowledge_base import KnowledgeArticle
from models.support_ticket import SupportTicket
from core.database import Base

async def migrate():
    async with engine.begin() as conn:
        # Ensure knowledge_articles is created
        await conn.run_sync(Base.metadata.create_all)
        print("Ensured all tables are created.")

        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'support_tickets';"))
        existing_columns = [r[0] for r in res.fetchall()]
        
        queries = [
            ("source", "ALTER TABLE support_tickets ADD COLUMN source VARCHAR DEFAULT 'website'"),
            ("ticket_stage", "ALTER TABLE support_tickets ADD COLUMN ticket_stage VARCHAR DEFAULT 'helpdesk'"),
            ("assigned_user_id", "ALTER TABLE support_tickets ADD COLUMN assigned_user_id INTEGER REFERENCES users(id)"),
            ("sla_status", "ALTER TABLE support_tickets ADD COLUMN sla_status VARCHAR DEFAULT 'on_track'"),
            ("customer_feedback_rating", "ALTER TABLE support_tickets ADD COLUMN customer_feedback_rating INTEGER"),
            ("customer_feedback_comments", "ALTER TABLE support_tickets ADD COLUMN customer_feedback_comments TEXT")
        ]
        
        for col, query in queries:
            if col not in existing_columns:
                try:
                    await conn.execute(text(query))
                    print(f"Added column {col} to support_tickets")
                except Exception as e:
                    print(f"Failed to add {col}: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
