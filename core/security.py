from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def decrypt_field(val: Optional[str]) -> Optional[str]:
    r"""
    Safely decrypts an encrypted database value (AES pkcs5 or Fernet),
    handling PostgreSQL asyncpg hex-encoded strings (\x...).
    Returns original value if not encrypted or if decryption fails.
    """
    if not val or not isinstance(val, str):
        return val
    val_str = val.strip()
    if '*' in val_str or len(val_str) < 16:
        return val_str

    cleaned = val_str
    if cleaned.startswith('\\x') or cleaned.startswith('\\\\x'):
        prefix = 3 if cleaned.startswith('\\\\x') else 2
        try:
            raw_bytes = bytes.fromhex(cleaned[prefix:])
            cleaned = raw_bytes.decode('utf-8', errors='ignore')
        except Exception:
            pass

    # Attempt AES pkcs5 decryption
    try:
        from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
        engine = AesEngine()
        engine._set_padding_mechanism('pkcs5')
        engine._update_key(settings.ENCRYPTION_KEY)
        decrypted = engine.decrypt(cleaned)
        if isinstance(decrypted, bytes):
            decrypted = decrypted.decode('utf-8')
        if decrypted:
            return str(decrypted)
    except Exception:
        pass

    # Attempt Fernet decryption fallback
    try:
        import base64
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(settings.ENCRYPTION_KEY.encode()[:32].ljust(32, b'0'))
        f = Fernet(key)
        decrypted = f.decrypt(cleaned.encode()).decode()
        if decrypted:
            return str(decrypted)
    except Exception:
        pass

    return val_str

