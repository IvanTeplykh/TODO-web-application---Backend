import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import UserModel
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRegisterResponse
from app.utils.encryption import compute_hash, encrypt_text


class AuthService:
    @staticmethod
    async def check_email_exists(session: AsyncSession, email: str) -> bool:
        e_hash = compute_hash(email.lower())
        stmt = select(UserModel).where(UserModel.email_hash == e_hash)
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def register_user(session: AsyncSession, user_in: UserCreate) -> UserRegisterResponse:
        # Check duplicate username
        u_stmt = select(UserModel).where(UserModel.username.ilike(user_in.username.strip()))
        u_res = await session.execute(u_stmt)
        if u_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

        email_lower = user_in.email.lower()
        e_hash = compute_hash(email_lower)
        stmt = select(UserModel).where(UserModel.email_hash == e_hash)
        res = await session.execute(stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        user_id = uuid.uuid4()
        hashed_password = get_password_hash(user_in.password)
        enc_email = encrypt_text(email_lower)
        
        new_user = UserModel(
            id=user_id,
            username=user_in.username,
            email=enc_email,
            email_hash=e_hash,
            password=hashed_password,
            avatar_url=None,
            created_at=datetime.now(timezone.utc)
        )
        
        session.add(new_user)
        await session.commit()
        return UserRegisterResponse(message="User created successfully")

    @staticmethod
    async def authenticate_user(session: AsyncSession, login_in: LoginRequest) -> Token:
        email_lower = login_in.email.lower()
        e_hash = compute_hash(email_lower)
        stmt = select(UserModel).where(UserModel.email_hash == e_hash)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user or not verify_password(login_in.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if login_in.remember_me:
            expires_delta = timedelta(days=settings.REMEMBER_ME_EXPIRE_DAYS)
        else:
            expires_delta = timedelta(days=settings.DEFAULT_TOKEN_EXPIRE_DAYS)
        
        access_token = create_access_token(subject=str(user.id), expires_delta=expires_delta)
        return Token(access_token=access_token)
