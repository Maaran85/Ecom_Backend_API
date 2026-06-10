import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from core.auth import create_access_token

async def get_test_token():
    # Customer 9
    from datetime import timedelta
    access_token_expires = timedelta(minutes=1000)
    access_token = create_access_token(
        data={"sub": "9", "role": "customer", "type": "access"}, 
        expires_delta=access_token_expires
    )
    print(access_token)

asyncio.run(get_test_token())
