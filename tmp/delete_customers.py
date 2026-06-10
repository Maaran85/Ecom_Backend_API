import asyncio
import sys
import os

# Add backend to path to import models
sys.path.append(os.getcwd())

from sqlalchemy import select, delete
from core.database import SessionLocal
from models.user import User, UserRole

async def delete_customer_role_data(dry_run=True):
    async with SessionLocal() as db:
        try:
            # 1. Query users with customer role
            stmt = select(User).where(User.role == UserRole.CUSTOMER)
            result = await db.execute(stmt)
            users_to_delete = result.scalars().all()
            
            count = len(users_to_delete)
            print(f"Found {count} users with role 'customer' in 'users' table.")
            
            if count == 0:
                print("No customer role users found. Nothing to delete.")
                return

            print("Sample users to be deleted:")
            for u in users_to_delete[:5]:
                print(f" - ID: {u.id}, Email: {u.email}, Name: {u.full_name}")

            if dry_run:
                print("\nDRY RUN: Records would be deleted but transaction will be rolled back.")
                await db.rollback()
                return

            # 2. Perform deletion
            delete_stmt = delete(User).where(User.role == UserRole.CUSTOMER)
            await db.execute(delete_stmt)
            
            await db.commit()
            print(f"\nSUCCESS: Deleted {count} users from 'users' table.")
            
        except Exception as e:
            await db.rollback()
            print(f"ERROR: {e}")
            raise

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Actually commit the changes")
    args = parser.parse_args()
    
    asyncio.run(delete_customer_role_data(dry_run=not args.commit))
