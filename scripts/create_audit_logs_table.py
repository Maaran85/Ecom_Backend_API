
import asyncio
from sqlalchemy import text
from core.database import engine

async def create_audit_logs_table():
    async with engine.begin() as conn:
        print("Creating audit_logs table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                dealer_id INTEGER REFERENCES dealers(id) ON DELETE SET NULL,
                action VARCHAR(50) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id VARCHAR(50),
                old_values JSON,
                new_values JSON,
                description TEXT,
                ip_address VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("Creating index on user_id, dealer_id and created_at...")
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_logs(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_dealer_id ON audit_logs(dealer_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at DESC)"))
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(create_audit_logs_table())
