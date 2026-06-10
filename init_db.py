"""
Database initialization script
Run this to create all tables in PostgreSQL
"""
import asyncio
from core.database import engine, Base
from models import *  # Import all models so they are registered with Base

async def init_db():
    """Create all database tables"""
    async with engine.begin() as conn:
        # Drop all tables (use with caution in production!)
        await conn.run_sync(Base.metadata.drop_all)
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    print("[SUCCESS] Database tables created successfully!")
    print("Tables: users, categories, products, cart_items, orders, order_items")

if __name__ == "__main__":
    asyncio.run(init_db())
