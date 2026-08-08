from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection_manager import connection_manager
from app.core.crypto import decrypt_field, encrypt_field
from app.core.database import get_db
from app.core.security import (
    get_password_hash,
    get_password_hash_async,
    verify_password,
    verify_password_async,
)
from app.dependencies.auth import get_current_user
from app.models.user import UserModel
from app.schemas.user import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    UserResponse,
    UserUpdate,
    VerifyPasswordRequest,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=list[UserResponse])
async def search_users(
    q: str = Query("", min_length=0),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    if not q or not q.strip():
        return []

    stmt = (
        select(UserModel)
        .where(
            and_(
                UserModel.username.ilike(f"%{q.strip()}%"),
                UserModel.id != current_user.id,
                UserModel.deleted_at == None
            )
        )
        .limit(10)
    )
    res = await session.execute(stmt)
    users = res.scalars().all()

    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=decrypt_field(u.email_encrypted) or u.email_encrypted,
            avatar_url=decrypt_field(u.avatar_url),
            chat_retention_days=u.chat_retention_days
        )
        for u in users
    ]


@router.put("/me", response_model=UserResponse)
@router.patch("/me", response_model=UserResponse)
async def update_profile(
    profile_in: UserUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id, UserModel.deleted_at == None)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if profile_in.username is not None and profile_in.username.strip() != user_db.username:
        new_username = profile_in.username.strip()
        u_stmt = select(UserModel).where(
            UserModel.username.ilike(new_username),
            UserModel.id != current_user.id,
            UserModel.deleted_at == None
        )
        u_res = await session.execute(u_stmt)
        if u_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        user_db.username = new_username

    if profile_in.avatar_url is not None:
        user_db.avatar_url = encrypt_field(profile_in.avatar_url) if profile_in.avatar_url else None

    if profile_in.chat_retention_days is not None:
        user_db.chat_retention_days = profile_in.chat_retention_days

    user_db.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user_db)

    await connection_manager.broadcast({
        "type": "user_profile_updated",
        "user_id": str(current_user.id),
        "username": profile_in.username,
        "avatar_url": profile_in.avatar_url
    })

    dec_email = decrypt_field(user_db.email_encrypted) or user_db.email_encrypted
    dec_avatar = decrypt_field(user_db.avatar_url)

    return UserResponse(
        id=user_db.id,
        username=user_db.username,
        email=dec_email,
        avatar_url=dec_avatar,
        chat_retention_days=user_db.chat_retention_days
    )


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id, UserModel.deleted_at == None)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not await verify_password_async(data.current_password, user_db.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )

    user_db.password_hash = await get_password_hash_async(data.new_password)
    user_db.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {"message": "Password changed successfully"}


@router.post("/verify-password")
async def verify_user_password(
    data: VerifyPasswordRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id, UserModel.deleted_at == None)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_valid = await verify_password_async(data.password, user_db.password_hash)
    return {"valid": is_valid}


@router.delete("/me")
async def delete_account(
    data: DeleteAccountRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    stmt = select(UserModel).where(UserModel.id == current_user.id, UserModel.deleted_at == None)
    res = await session.execute(stmt)
    user_db = res.scalar_one_or_none()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not await verify_password_async(data.password, user_db.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )

    await TaskService.reassign_tasks_before_user_deletion(session, current_user.id)
    user_db.deleted_at = datetime.now(timezone.utc)
    await session.commit()

    return {"message": "Account deleted successfully"}
