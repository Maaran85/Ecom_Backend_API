
import asyncio
from sqlalchemy import text
from core.database import engine

async def upgrade_hubs_extra_fields():
    async with engine.begin() as conn:
        print("Checking for extra fields in delivery_hubs table...")
        
        # Check existing columns
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'delivery_hubs'"))
        columns = [row[0] for row in result.fetchall()]
        
        new_columns = {
            'hub_type': 'VARCHAR',
            'capacity': 'VARCHAR',
            'operating_hours': 'VARCHAR',
            'emergency_phone': 'VARCHAR'
        }
        
        for col, dtype in new_columns.items():
            if col not in columns:
                print(f"Adding column {col}...")
                await conn.execute(text(f"ALTER TABLE delivery_hubs ADD COLUMN {col} {dtype}"))
            else:
                print(f"Column {col} already exists.")
        
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(upgrade_hubs_extra_fields())
