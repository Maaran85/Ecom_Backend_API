from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "OnlineshopApp"
    BASE_URL: str = "http://localhost:8000"
    
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    SECRET_KEY: str = "supersecretkey1234567890"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # SMTP Settings (optional)
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SENDER_EMAIL: Optional[str] = None
    SENDER_PASSWORD: Optional[str] = None
    SENDER_NAME: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env

settings = Settings()
