from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime
import re

class CustomerBase(BaseModel):
    full_name: str = Field(..., min_length=3, description="Full name must be at least 3 characters")
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=10, max_length=10, description="Phone must be exactly 10 digits")
    dob: Optional[str] = None

    @validator('phone')
    def phone_must_be_digits(cls, v):
        if not re.match(r'^\d{10}$', v):
            raise ValueError('Phone must be 10 digits')
        return v

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    is_active: bool
    created_at: datetime
    role: str = "customer"

    class Config:
        from_attributes = True

class CustomerLoginRequest(BaseModel):
    identifier: str # email or phone

class CustomerRegisterRequest(BaseModel):
    identifier: str # 10-digit phone
    full_name: Optional[str] = None
    password: Optional[str] = None
    referral_code: Optional[str] = None

class CustomerPasswordLogin(BaseModel):
    identifier: str # email or phone
    password: str

class CustomerOTPVerify(BaseModel):
    identifier: str
    otp: str
    full_name: Optional[str] = None # Used for registration
    password: Optional[str] = None # Password set during registration
    referral_code: Optional[str] = None

class CustomerForgotPasswordRequest(BaseModel):
    identifier: str # email or phone

class CustomerForgotPasswordVerify(BaseModel):
    identifier: str
    otp: str

class CustomerResetPassword(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
