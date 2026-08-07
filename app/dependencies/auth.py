from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_field
from app.core.database import get_db
from app.models.user import UserModel
from app.schemas.auth import TokenData
from app.schemas.user import UserResponse

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    session: AsyncSession = Depends(get_db)
) -> UserResponse:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id)
    except JWTError:
        raise credentials_exception

    try:
        user_uuid = UUID(token_data.user_id)
    except ValueError:
        raise credentials_exception

    stmt = select(UserModel).where(UserModel.id == user_uuid, UserModel.deleted_at == None)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    dec_email = decrypt_field(user.email_encrypted) or user.email_encrypted
    dec_avatar = decrypt_field(user.avatar_url)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=dec_email,
        avatar_url=dec_avatar,
        chat_retention_days=user.chat_retention_days
    )
