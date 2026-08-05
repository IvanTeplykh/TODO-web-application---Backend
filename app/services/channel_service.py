import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete, func
from sqlalchemy.orm import selectinload

from app.models.channel import ChannelModel, ChannelMemberModel, ChannelMessageModel
from app.models.user import UserModel
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelMemberResponse,
    ChannelInviteResponse,
    ChannelMessageResponse
)
from app.utils.encryption import encrypt_text, decrypt_text, compute_hash

class ChannelService:
    @staticmethod
    async def get_member_role(session: AsyncSession, channel_id: UUID, user_id: UUID) -> Optional[str]:
        stmt = select(ChannelMemberModel.role).where(
            and_(
                ChannelMemberModel.channel_id == channel_id,
                ChannelMemberModel.user_id == user_id,
                ChannelMemberModel.status == "accepted"
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def is_admin_or_owner(session: AsyncSession, channel_id: UUID, user_id: UUID) -> bool:
        role = await ChannelService.get_member_role(session, channel_id, user_id)
        return role in ["owner", "admin"]

    @staticmethod
    async def create_channel(session: AsyncSession, owner_id: UUID, data: ChannelCreate) -> ChannelResponse:
        channel_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        channel = ChannelModel(
            id=channel_id,
            name=data.name.strip(),
            description=data.description.strip() if data.description else None,
            avatar_url=data.avatar_url.strip() if data.avatar_url else None,
            owner_id=owner_id,
            created_at=now
        )
        session.add(channel)

        owner_member = ChannelMemberModel(
            id=uuid.uuid4(),
            channel_id=channel_id,
            user_id=owner_id,
            role="owner",
            status="accepted",
            joined_at=now
        )
        session.add(owner_member)

        await session.commit()
        await session.refresh(channel)

        return ChannelResponse(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            avatar_url=channel.avatar_url,
            owner_id=channel.owner_id,
            created_at=channel.created_at,
            my_role="owner",
            members_count=1
        )

    @staticmethod
    async def get_user_channels(session: AsyncSession, user_id: UUID) -> List[ChannelResponse]:
        stmt = (
            select(ChannelModel, ChannelMemberModel.role)
            .join(ChannelMemberModel, ChannelMemberModel.channel_id == ChannelModel.id)
            .where(
                and_(
                    ChannelMemberModel.user_id == user_id,
                    ChannelMemberModel.status == "accepted"
                )
            )
            .order_by(ChannelModel.created_at.desc())
        )
        res = await session.execute(stmt)
        rows = res.all()

        channels = []
        for channel, role in rows:
            count_stmt = select(func.count(ChannelMemberModel.id)).where(ChannelMemberModel.channel_id == channel.id)
            count_res = await session.execute(count_stmt)
            m_count = count_res.scalar_one() or 0

            channels.append(
                ChannelResponse(
                    id=channel.id,
                    name=channel.name,
                    description=channel.description,
                    avatar_url=channel.avatar_url,
                    owner_id=channel.owner_id,
                    created_at=channel.created_at,
                    my_role=role,
                    members_count=m_count
                )
            )
        return channels

    @staticmethod
    async def get_channel_members(session: AsyncSession, channel_id: UUID, user_id: UUID) -> List[ChannelMemberResponse]:
        role = await ChannelService.get_member_role(session, channel_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this channel")

        stmt = (
            select(ChannelMemberModel)
            .options(selectinload(ChannelMemberModel.user))
            .where(ChannelMemberModel.channel_id == channel_id)
            .order_by(ChannelMemberModel.joined_at.asc())
        )
        res = await session.execute(stmt)
        members = res.scalars().all()

        results = []
        for m in members:
            u_name = m.user.username if m.user else "Unknown"
            u_avatar = m.user.avatar_url if m.user else None
            results.append(
                ChannelMemberResponse(
                    id=m.id,
                    user_id=m.user_id,
                    username=u_name,
                    avatar_url=u_avatar,
                    role=m.role,
                    status=m.status,
                    joined_at=m.joined_at
                )
            )
        return results

    @staticmethod
    async def update_channel(session: AsyncSession, channel_id: UUID, user_id: UUID, data: ChannelUpdate) -> ChannelResponse:
        is_admin = await ChannelService.is_admin_or_owner(session, channel_id, user_id)
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel admins/owners can update channel details")

        stmt = select(ChannelModel).where(ChannelModel.id == channel_id)
        res = await session.execute(stmt)
        channel = res.scalar_one_or_none()

        if not channel:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

        if data.name is not None:
            channel.name = data.name.strip()
        if data.description is not None:
            channel.description = data.description.strip() if data.description else None
        if data.avatar_url is not None:
            channel.avatar_url = data.avatar_url.strip() if data.avatar_url and data.avatar_url.strip() else None

        await session.commit()
        await session.refresh(channel)

        role = await ChannelService.get_member_role(session, channel_id, user_id)
        count_stmt = select(func.count(ChannelMemberModel.id)).where(ChannelMemberModel.channel_id == channel.id)
        count_res = await session.execute(count_stmt)
        m_count = count_res.scalar_one() or 0

        return ChannelResponse(
            id=channel.id,
            name=channel.name,
            description=channel.description,
            avatar_url=channel.avatar_url,
            owner_id=channel.owner_id,
            created_at=channel.created_at,
            my_role=role,
            members_count=m_count
        )

    @staticmethod
    async def delete_channel(session: AsyncSession, channel_id: UUID, user_id: UUID) -> dict:
        role = await ChannelService.get_member_role(session, channel_id, user_id)
        if role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel owner can delete the channel")

        stmt = select(ChannelModel).where(ChannelModel.id == channel_id)
        res = await session.execute(stmt)
        channel = res.scalar_one_or_none()

        if not channel:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

        await session.delete(channel)
        await session.commit()
        return {"message": "Channel deleted successfully", "id": str(channel_id)}

    @staticmethod
    async def add_member(
        session: AsyncSession,
        channel_id: UUID,
        actor_id: UUID,
        target_user_id: Optional[UUID] = None,
        target_username: Optional[str] = None
    ) -> ChannelMemberResponse:
        is_admin = await ChannelService.is_admin_or_owner(session, channel_id, actor_id)
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel admins/owners can send invitations")

        if target_user_id:
            u_stmt = select(UserModel).where(UserModel.id == target_user_id)
        elif target_username:
            u_stmt = select(UserModel).where(func.lower(UserModel.username) == target_username.strip().lower())
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User ID or username is required")

        u_res = await session.execute(u_stmt)
        target_user = u_res.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        existing_stmt = select(ChannelMemberModel).where(
            and_(ChannelMemberModel.channel_id == channel_id, ChannelMemberModel.user_id == target_user.id)
        )
        ex_res = await session.execute(existing_stmt)
        existing_member = ex_res.scalar_one_or_none()
        if existing_member:
            if existing_member.status == "accepted":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member of this channel")
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation already sent to this user")

        new_member = ChannelMemberModel(
            id=uuid.uuid4(),
            channel_id=channel_id,
            user_id=target_user.id,
            role="member",
            status="pending",
            joined_at=datetime.now(timezone.utc)
        )
        session.add(new_member)
        await session.commit()
        await session.refresh(new_member)

        return ChannelMemberResponse(
            id=new_member.id,
            user_id=target_user.id,
            username=target_user.username,
            avatar_url=target_user.avatar_url,
            role="member",
            status="pending",
            joined_at=new_member.joined_at
        )

    @staticmethod
    async def get_pending_invites(session: AsyncSession, user_id: UUID) -> List[ChannelInviteResponse]:
        stmt = (
            select(ChannelMemberModel)
            .options(selectinload(ChannelMemberModel.channel))
            .where(
                and_(
                    ChannelMemberModel.user_id == user_id,
                    ChannelMemberModel.status == "pending"
                )
            )
            .order_by(ChannelMemberModel.joined_at.desc())
        )
        res = await session.execute(stmt)
        members = res.scalars().all()

        results = []
        for m in members:
            if m.channel:
                results.append(
                    ChannelInviteResponse(
                        id=m.id,
                        channel_id=m.channel_id,
                        channel_name=m.channel.name,
                        channel_description=m.channel.description,
                        channel_avatar=m.channel.avatar_url,
                        created_at=m.joined_at
                    )
                )
        return results

    @staticmethod
    async def respond_to_invite(session: AsyncSession, invite_id: UUID, user_id: UUID, action: str) -> dict:
        stmt = select(ChannelMemberModel).where(
            and_(
                ChannelMemberModel.id == invite_id,
                ChannelMemberModel.user_id == user_id,
                ChannelMemberModel.status == "pending"
            )
        )
        res = await session.execute(stmt)
        member = res.scalar_one_or_none()

        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel invitation not found")

        ch_id = member.channel_id

        if action == "accept":
            member.status = "accepted"
            await session.commit()
            return {"message": "Channel invitation accepted", "channel_id": str(ch_id), "status": "accepted"}
        elif action == "decline":
            await session.delete(member)
            await session.commit()
            return {"message": "Channel invitation declined", "channel_id": str(ch_id), "status": "declined"}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")

    @staticmethod
    async def remove_member(session: AsyncSession, channel_id: UUID, actor_id: UUID, target_user_id: UUID) -> dict:
        actor_role = await ChannelService.get_member_role(session, channel_id, actor_id)
        if not actor_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a member of this channel")

        if actor_id != target_user_id and actor_role not in ["owner", "admin"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel admins/owners can remove other members")

        m_stmt = select(ChannelMemberModel).where(
            and_(ChannelMemberModel.channel_id == channel_id, ChannelMemberModel.user_id == target_user_id)
        )
        m_res = await session.execute(m_stmt)
        target_member = m_res.scalar_one_or_none()

        if not target_member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in channel")

        if target_member.role == "owner":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Channel owner cannot be removed")

        await session.delete(target_member)
        await session.commit()
        return {"message": "Member removed successfully", "user_id": str(target_user_id), "channel_id": str(channel_id)}

    @staticmethod
    async def update_member_role(session: AsyncSession, channel_id: UUID, actor_id: UUID, target_user_id: UUID, new_role: str) -> ChannelMemberResponse:
        actor_role = await ChannelService.get_member_role(session, channel_id, actor_id)
        if actor_role not in ["owner", "admin"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only channel admins/owners can manage roles")

        m_stmt = select(ChannelMemberModel).options(selectinload(ChannelMemberModel.user)).where(
            and_(ChannelMemberModel.channel_id == channel_id, ChannelMemberModel.user_id == target_user_id)
        )
        m_res = await session.execute(m_stmt)
        target_member = m_res.scalar_one_or_none()

        if not target_member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in channel")

        if target_member.role == "owner":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change role of channel owner")

        target_member.role = new_role
        await session.commit()
        await session.refresh(target_member)

        u_name = target_member.user.username if target_member.user else "Unknown"
        u_avatar = target_member.user.avatar_url if target_member.user else None

        return ChannelMemberResponse(
            id=target_member.id,
            user_id=target_member.user_id,
            username=u_name,
            avatar_url=u_avatar,
            role=target_member.role,
            status=target_member.status,
            joined_at=target_member.joined_at
        )

    @staticmethod
    async def create_channel_message(session: AsyncSession, channel_id: UUID, sender_id: UUID, content: str) -> ChannelMessageResponse:
        role = await ChannelService.get_member_role(session, channel_id, sender_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must be a channel member to post messages")

        u_stmt = select(UserModel).where(UserModel.id == sender_id)
        u_res = await session.execute(u_stmt)
        sender_user = u_res.scalar_one_or_none()

        msg_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        enc_content = encrypt_text(content)
        c_hash = compute_hash(content)

        msg = ChannelMessageModel(
            id=msg_id,
            channel_id=channel_id,
            sender_id=sender_id,
            content=enc_content,
            content_hash=c_hash,
            is_edited=False,
            created_at=now,
            updated_at=None
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

        return ChannelMessageResponse(
            id=msg.id,
            channel_id=msg.channel_id,
            sender_id=msg.sender_id,
            sender_name=sender_user.username if sender_user else "Unknown",
            sender_avatar=sender_user.avatar_url if sender_user else None,
            content=content,
            content_hash=c_hash,
            created_at=msg.created_at,
            is_edited=False,
            updated_at=None
        )

    @staticmethod
    async def get_channel_messages(session: AsyncSession, channel_id: UUID, user_id: UUID, limit: int = 100) -> List[ChannelMessageResponse]:
        role = await ChannelService.get_member_role(session, channel_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must be a channel member to view messages")

        stmt = (
            select(ChannelMessageModel)
            .options(selectinload(ChannelMessageModel.sender))
            .where(ChannelMessageModel.channel_id == channel_id)
            .order_by(ChannelMessageModel.created_at.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        messages = res.scalars().all()

        results = []
        for msg in messages:
            plain_content = decrypt_text(msg.content) or ""
            s_name = msg.sender.username if msg.sender else "Unknown"
            s_avatar = msg.sender.avatar_url if msg.sender else None
            results.append(
                ChannelMessageResponse(
                    id=msg.id,
                    channel_id=msg.channel_id,
                    sender_id=msg.sender_id,
                    sender_name=s_name,
                    sender_avatar=s_avatar,
                    content=plain_content,
                    content_hash=msg.content_hash or compute_hash(plain_content),
                    created_at=msg.created_at,
                    is_edited=msg.is_edited,
                    updated_at=msg.updated_at
                )
            )
        return results

    @staticmethod
    async def edit_channel_message(session: AsyncSession, channel_id: UUID, message_id: UUID, sender_id: UUID, new_content: str) -> ChannelMessageResponse:
        stmt = select(ChannelMessageModel).options(selectinload(ChannelMessageModel.sender)).where(
            and_(ChannelMessageModel.id == message_id, ChannelMessageModel.channel_id == channel_id)
        )
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg.sender_id != sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's message")

        updated_at = datetime.now(timezone.utc)
        enc_content = encrypt_text(new_content)
        c_hash = compute_hash(new_content)

        msg.content = enc_content
        msg.content_hash = c_hash
        msg.is_edited = True
        msg.updated_at = updated_at

        await session.commit()
        await session.refresh(msg)

        s_name = msg.sender.username if msg.sender else "Unknown"
        s_avatar = msg.sender.avatar_url if msg.sender else None

        return ChannelMessageResponse(
            id=msg.id,
            channel_id=msg.channel_id,
            sender_id=msg.sender_id,
            sender_name=s_name,
            sender_avatar=s_avatar,
            content=new_content,
            content_hash=c_hash,
            created_at=msg.created_at,
            is_edited=msg.is_edited,
            updated_at=msg.updated_at
        )

    @staticmethod
    async def delete_channel_message(session: AsyncSession, channel_id: UUID, message_id: UUID, actor_id: UUID) -> dict:
        stmt = select(ChannelMessageModel).where(
            and_(ChannelMessageModel.id == message_id, ChannelMessageModel.channel_id == channel_id)
        )
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        # Check if actor is sender OR admin/owner
        is_sender = (msg.sender_id == actor_id)
        is_admin = await ChannelService.is_admin_or_owner(session, channel_id, actor_id)

        if not is_sender and not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must be message sender or channel admin to delete message")

        await session.delete(msg)
        await session.commit()

        return {"message": "Channel message deleted", "id": str(message_id), "channel_id": str(channel_id)}

channel_service = ChannelService()
