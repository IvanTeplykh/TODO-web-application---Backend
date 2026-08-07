import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import compute_hmac_index, encrypt_field
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import UserModel
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRegisterResponse


class AuthService:
    @staticmethod
    async def check_email_exists(session: AsyncSession, email: str) -> bool:
        e_index = compute_hmac_index(email)
        stmt = select(UserModel).where(UserModel.email_index == e_index, UserModel.deleted_at == None)
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def register_user(session: AsyncSession, user_in: UserCreate) -> UserRegisterResponse:
        u_stmt = select(UserModel).where(
            UserModel.username.ilike(user_in.username.strip()),
            UserModel.deleted_at == None
        )
        u_res = await session.execute(u_stmt)
        if u_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

        email_clean = user_in.email.strip().lower()
        e_index = compute_hmac_index(email_clean)
        stmt = select(UserModel).where(UserModel.email_index == e_index, UserModel.deleted_at == None)
        res = await session.execute(stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        user_id = uuid.uuid4()
        hashed_password = get_password_hash(user_in.password)
        enc_email = encrypt_field(email_clean)

        new_user = UserModel(
            id=user_id,
            username=user_in.username.strip(),
            email_encrypted=enc_email,
            email_index=e_index,
            password_hash=hashed_password,
            avatar_url=None,
            created_at=datetime.now(timezone.utc)
        )

        session.add(new_user)
        await session.commit()
        return UserRegisterResponse(message="User created successfully")

    @staticmethod
    async def authenticate_user(session: AsyncSession, login_in: LoginRequest) -> Token:
        email_clean = login_in.email.strip().lower()
        e_index = compute_hmac_index(email_clean)
        stmt = select(UserModel).where(UserModel.email_index == e_index, UserModel.deleted_at == None)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if not user or not verify_password(login_in.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user.last_login_at = datetime.now(timezone.utc)
        await session.commit()

        if login_in.remember_me:
            expires_delta = timedelta(days=settings.REMEMBER_ME_EXPIRE_DAYS)
        else:
            expires_delta = timedelta(days=settings.DEFAULT_TOKEN_EXPIRE_DAYS)

        access_token = create_access_token(subject=str(user.id), expires_delta=expires_delta)
        return Token(access_token=access_token)
