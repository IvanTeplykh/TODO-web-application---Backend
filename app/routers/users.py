from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas.user import UserResponse, UserUpdate, ChangePasswordRequest, VerifyPasswordRequest
from app.dependencies.auth import get_current_user
from app.core.database import get_db
from app.models.user import UserModel
from app.core.security import verify_password, get_password_hash
from app.core.connection_manager import connection_manager

router = APIRouter(prefix="/users", tags=["users"])

@router.put("/me", response_model=UserResponse)
@router.patch("/me", response_model=UserResponse)
async def update_profile(
    profile_in: UserUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_db.username = profile_in.username
    user_db.avatar_url = profile_in.avatar_url
    user_db.chat_retention_days = profile_in.chat_retention_days
    await session.commit()
    await session.refresh(user_db)

    # Broadcast real-time profile update to all connected WebSocket clients
    await connection_manager.broadcast({
        "type": "user_profile_updated",
        "user_id": str(current_user.id),
        "username": profile_in.username,
        "avatar_url": profile_in.avatar_url
    })
    
    return UserResponse(
        id=user_db.id,
        username=user_db.username,
        email=user_db.email,
        avatar_url=user_db.avatar_url,
        chat_retention_days=user_db.chat_retention_days
    )

@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    if not verify_password(data.current_password, user_db.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
        
    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )
        
    user_db.password = get_password_hash(data.new_password)
    await session.commit()
    
    return {"message": "Password changed successfully"}

@router.post("/verify-password")
async def verify_user_password(
    data: VerifyPasswordRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    is_valid = verify_password(data.password, user_db.password)
    return {"valid": is_valid}
