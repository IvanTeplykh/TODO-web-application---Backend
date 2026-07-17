from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import settings
from app.core.database import db
from app.schemas.auth import TokenData
from app.schemas.user import UserResponse
from uuid import UUID

security_scheme = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> UserResponse:
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

    user = await db.users_collection.find_one({"_id": str(user_uuid)})
    if user is None:
        raise credentials_exception
    
    return UserResponse(
        id=UUID(user["_id"]),
        username=user["username"],
        email=user["email"],
        avatar_url=user.get("avatar_url")
    )
