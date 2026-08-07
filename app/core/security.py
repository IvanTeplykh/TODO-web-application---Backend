from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from jose import jwt

from app.core.config import settings

ph = PasswordHasher()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except Exception:
        try:
            import bcrypt
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False


def get_password_hash(password: str) -> str:
    return ph.hash(password)


def get_passcode_hash(passcode: str) -> str:
    return ph.hash(passcode)


def verify_passcode(plain_passcode: str, hashed_passcode: str) -> bool:
    try:
        return ph.verify(hashed_passcode, plain_passcode)
    except Exception:
        return False


def create_access_token(subject: str | Any, expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
