import asyncio
import os
import sys

# Ensure root directory is on Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal, engine
from core.security import get_password_hash, verify_password
from models.customer_user import CustomerUser
from sqlalchemy import select, update, text


async def backfill_customer_default_passwords(default_plain_pwd: str = "user123"):
    """
    Assigns the Argon2 hash of default_plain_pwd to all existing customer_users
    records that do not currently have a password_hash set.
    Safe, repeatable, and idempotent.
    """
    print(f"--- Starting Customer Password Backfill ---")
    print(f"Target Database: onlineshopappdb (engine: {engine.url.render_as_string(hide_password=True)})")
    
    # Generate Argon2 hash using core.security utility
    pwd_hash = get_password_hash(default_plain_pwd)
    print("Generated Argon2 password hash successfully (plain text never stored).")
    
    # Self-test the generated hash
    assert verify_password(default_plain_pwd, pwd_hash), "Sanity check failed: verify_password returned False!"
    
    updated_count = 0
    skipped_count = 0
    failed_count = 0

    async with SessionLocal() as session:
        try:
            # Query all customer_users
            result = await session.execute(
                select(CustomerUser).order_by(CustomerUser.id.asc())
            )
            customers = result.scalars().all()
            total_found = len(customers)
            print(f"Total customer records found in customer_users: {total_found}")

            for customer in customers:
                try:
                    # Do not overwrite if a password_hash is already set
                    if customer.password_hash and customer.password_hash.strip():
                        skipped_count += 1
                    else:
                        customer.password_hash = pwd_hash
                        if customer.failed_login_attempts is None:
                            customer.failed_login_attempts = 0
                        updated_count += 1
                except Exception as ex:
                    print(f"Error preparing customer ID {customer.id}: {ex}")
                    failed_count += 1

            await session.commit()
            print("Database transaction committed successfully.")

        except Exception as e:
            await session.rollback()
            print(f"FATAL: Database error during backfill: {e}")
            raise e

    print(f"\n--- Backfill Summary ---")
    print(f"Total customer records: {total_found}")
    print(f"Records updated:        {updated_count}")
    print(f"Records skipped:        {skipped_count}")
    print(f"Records failed:         {failed_count}")
    
    # Verification pass: query records and verify
    async with SessionLocal() as session:
        check_res = await session.execute(
            select(CustomerUser.id, CustomerUser.phone, CustomerUser.full_name, CustomerUser.password_hash, CustomerUser.is_active)
            .order_by(CustomerUser.id.asc())
            .limit(5)
        )
        sample = check_res.all()
        print("\nVerification Sample (First 5 records):")
        for cid, phone, name, h, active in sample:
            is_valid = verify_password(default_plain_pwd, h) if h else False
            masked_hash = f"{h[:15]}...{h[-10:]}" if h else "None"
            print(f"  ID: {cid} | Phone: {phone} | Active: {active} | Hash: {masked_hash} | Verified: {is_valid}")

    return {
        "total": total_found,
        "updated": updated_count,
        "skipped": skipped_count,
        "failed": failed_count
    }


if __name__ == "__main__":
    asyncio.run(backfill_customer_default_passwords("user123"))
