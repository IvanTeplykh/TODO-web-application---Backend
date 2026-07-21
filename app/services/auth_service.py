import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.database import db
from app.core.security import get_password_hash, verify_password, create_access_token
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRegisterResponse

class AuthService:
    @staticmethod
    async def check_email_exists(email: str) -> bool:
        email_lower = email.lower()
        existing_user = await db.users_collection.find_one({"email": email_lower})
        return existing_user is not None

    @staticmethod
    async def register_user(user_in: UserCreate) -> UserRegisterResponse:
        email_lower = user_in.email.lower()
        existing_user = await db.users_collection.find_one({"email": email_lower})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(user_in.password)
        
        user_doc = {
            "_id": user_id,
            "username": user_in.username,
            "email": email_lower,
            "password": hashed_password,
            "avatar_url": None,
            "created_at": datetime.now(timezone.utc)
        }
        
        await db.users_collection.insert_one(user_doc)
        return UserRegisterResponse(message="User created successfully")

    @staticmethod
    async def authenticate_user(login_in: LoginRequest) -> Token:
        email_lower = login_in.email.lower()
        user = await db.users_collection.find_one({"email": email_lower})
        if not user or not verify_password(login_in.password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if login_in.remember_me:
            expires_delta = timedelta(days=settings.REMEMBER_ME_EXPIRE_DAYS)
        else:
            expires_delta = timedelta(days=settings.DEFAULT_TOKEN_EXPIRE_DAYS)
        
        access_token = create_access_token(subject=user["_id"], expires_delta=expires_delta)
        return Token(access_token=access_token)
