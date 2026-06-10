from pydantic import BaseModel
from typing import Optional, Any

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[Any] = None

class TokenData(BaseModel):
    email: str | None = None

class LoginRequest(BaseModel):
    identifier: str
    password: str
