from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.schemas.user import UserResponse
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelMemberResponse,
    AddMemberRequest,
    UpdateMemberRoleRequest,
    ChannelMessageCreate,
    ChannelMessageUpdate,
    ChannelMessageResponse
)
from app.services.channel_service import channel_service
from app.core.connection_manager import connection_manager

router = APIRouter(prefix="/channels", tags=["channels"])

@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: ChannelCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await channel_service.create_channel(session, current_user.id, data)

@router.get("", response_model=List[ChannelResponse])
async def get_my_channels(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await channel_service.get_user_channels(session, current_user.id)

@router.get("/{channel_id}/members", response_model=List[ChannelMemberResponse])
async def get_channel_members(
    channel_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await channel_service.get_channel_members(session, channel_id, current_user.id)

@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: UUID,
    data: ChannelUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    updated = await channel_service.update_channel(session, channel_id, current_user.id, data)
    # Broadcast channel updated event
    await connection_manager.broadcast({
        "type": "channel_updated",
        "channel": updated.model_dump(mode="json")
    })
    return updated

@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.delete_channel(session, channel_id, current_user.id)
    await connection_manager.broadcast({
        "type": "channel_deleted",
        "channel_id": str(channel_id)
    })
    return res

@router.post("/{channel_id}/members", response_model=ChannelMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    channel_id: UUID,
    data: AddMemberRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.add_member(session, channel_id, current_user.id, data.user_id)
    await connection_manager.broadcast({
        "type": "channel_member_added",
        "channel_id": str(channel_id),
        "member": res.model_dump(mode="json")
    })
    return res

@router.delete("/{channel_id}/members/{target_user_id}")
async def remove_member(
    channel_id: UUID,
    target_user_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.remove_member(session, channel_id, current_user.id, target_user_id)
    await connection_manager.broadcast({
        "type": "channel_member_removed",
        "channel_id": str(channel_id),
        "user_id": str(target_user_id)
    })
    return res

@router.patch("/{channel_id}/members/{target_user_id}/role", response_model=ChannelMemberResponse)
async def update_member_role(
    channel_id: UUID,
    target_user_id: UUID,
    data: UpdateMemberRoleRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.update_member_role(session, channel_id, current_user.id, target_user_id, data.role)
    await connection_manager.broadcast({
        "type": "channel_member_role_updated",
        "channel_id": str(channel_id),
        "member": res.model_dump(mode="json")
    })
    return res

@router.get("/{channel_id}/messages", response_model=List[ChannelMessageResponse])
async def get_channel_messages(
    channel_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await channel_service.get_channel_messages(session, channel_id, current_user.id, limit)

@router.post("/{channel_id}/messages", response_model=ChannelMessageResponse, status_code=status.HTTP_201_CREATED)
async def post_channel_message(
    channel_id: UUID,
    data: ChannelMessageCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.create_channel_message(session, channel_id, current_user.id, data.content)
    msg_payload = {
        "type": "new_channel_message",
        "message": res.model_dump(mode="json")
    }
    await connection_manager.broadcast(msg_payload)
    return res

@router.patch("/{channel_id}/messages/{message_id}", response_model=ChannelMessageResponse)
async def edit_channel_message(
    channel_id: UUID,
    message_id: UUID,
    data: ChannelMessageUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.edit_channel_message(session, channel_id, message_id, current_user.id, data.content)
    msg_payload = {
        "type": "channel_message_edited",
        "message": res.model_dump(mode="json")
    }
    await connection_manager.broadcast(msg_payload)
    return res

@router.delete("/{channel_id}/messages/{message_id}")
async def delete_channel_message(
    channel_id: UUID,
    message_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await channel_service.delete_channel_message(session, channel_id, message_id, current_user.id)
    msg_payload = {
        "type": "channel_message_deleted",
        "channel_id": str(channel_id),
        "message_id": str(message_id)
    }
    await connection_manager.broadcast(msg_payload)
    return res
