import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.connection_manager import connection_manager
from app.core.crypto import compute_hmac_index, decrypt_field, encrypt_field
from app.models.channel import ChannelMemberModel
from app.models.chat import ChatMessageModel, ChatRequestModel
from app.models.global_chat import GlobalChatMessageModel
from app.models.user import UserModel
from app.schemas.chat import (
    ChatRequestAction,
    ChatRequestResponse,
    ChatUser,
    MessageCreate,
    MessageResponse,
)


def _str(val) -> str:
    if val is None:
        return ""
    return val.value if hasattr(val, "value") else str(val)


GLOBAL_CHAT_RETENTION_DAYS = 180


class ChatService:
    @staticmethod
    async def cleanup_expired_global_messages(session: AsyncSession) -> int:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=GLOBAL_CHAT_RETENTION_DAYS)
        stmt = delete(GlobalChatMessageModel).where(GlobalChatMessageModel.created_at < cutoff_date)
        res = await session.execute(stmt)
        return res.rowcount or 0

    @staticmethod
    async def can_users_chat(session: AsyncSession, user_a: UUID, recipient_id_str: str) -> bool:
        if recipient_id_str == "global":
            return True
        try:
            recipient_uuid = UUID(recipient_id_str)
        except ValueError:
            return False

        c_stmt = select(ChannelMemberModel).where(
            and_(
                ChannelMemberModel.channel_id == recipient_uuid,
                ChannelMemberModel.user_id == user_a,
                ChannelMemberModel.status == "accepted"
            )
        )
        c_res = await session.execute(c_stmt)
        if c_res.scalar_one_or_none() is not None:
            return True

        stmt = select(ChatRequestModel).where(
            and_(
                ChatRequestModel.status == "accepted",
                or_(
                    and_(ChatRequestModel.requester_id == user_a, ChatRequestModel.recipient_id == recipient_uuid),
                    and_(ChatRequestModel.requester_id == recipient_uuid, ChatRequestModel.recipient_id == user_a)
                )
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def create_message(
        session: AsyncSession,
        sender_id: UUID,
        data: MessageCreate
    ) -> MessageResponse:
        message_id = uuid.uuid4()
        created_at = datetime.now(timezone.utc)
        enc_content = encrypt_field(data.content)
        c_index = compute_hmac_index(data.content)

        sender_stmt = select(UserModel).where(UserModel.id == sender_id, UserModel.deleted_at == None)
        sender_res = await session.execute(sender_stmt)
        sender_user = sender_res.scalar_one_or_none()
        sender_name = sender_user.username if sender_user else "Unknown"
        sender_avatar = decrypt_field(sender_user.avatar_url) if (sender_user and sender_user.avatar_url) else None

        if data.recipient_id == "global":
            await ChatService.cleanup_expired_global_messages(session)

            new_msg = GlobalChatMessageModel(
                id=message_id,
                sender_id=sender_id,
                recipient_id="global",
                content=enc_content,
                content_hash=c_index,
                is_edited=False,
                created_at=created_at,
                updated_at=None
            )
            session.add(new_msg)
            await session.commit()
            await session.refresh(new_msg)
        else:
            rec_user_id = None
            chan_id = None
            try:
                r_uuid = UUID(data.recipient_id)
                c_stmt = select(ChannelMemberModel).where(ChannelMemberModel.channel_id == r_uuid)
                c_res = await session.execute(c_stmt)
                if c_res.scalars().first():
                    chan_id = r_uuid
                else:
                    rec_user_id = r_uuid
            except ValueError:
                pass

            new_msg = ChatMessageModel(
                id=message_id,
                sender_id=sender_id,
                recipient_user_id=rec_user_id,
                channel_id=chan_id,
                content_encrypted=enc_content,
                content_index=c_index,
                is_edited=False,
                created_at=created_at,
                edited_at=None,
                deleted_at=None
            )
            session.add(new_msg)
            await session.commit()
            await session.refresh(new_msg)

        return MessageResponse(
            id=message_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_avatar=sender_avatar,
            recipient_id=data.recipient_id,
            content=data.content,
            content_hash=c_index,
            created_at=created_at,
            is_edited=False,
            updated_at=None
        )

    @staticmethod
    async def get_messages(session: AsyncSession, user_id: UUID, recipient_id: str, limit: int = 100) -> list[MessageResponse]:
        if recipient_id == "global":
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=GLOBAL_CHAT_RETENTION_DAYS)
            await ChatService.cleanup_expired_global_messages(session)

            gc_stmt = (
                select(GlobalChatMessageModel)
                .options(selectinload(GlobalChatMessageModel.sender))
                .where(GlobalChatMessageModel.created_at >= cutoff_date)
                .order_by(GlobalChatMessageModel.created_at.asc())
                .limit(limit)
            )
            gc_res = await session.execute(gc_stmt)
            gc_docs = gc_res.scalars().all()

            results = []
            for msg in gc_docs:
                s_name = msg.sender.username if msg.sender else "Unknown"
                s_avatar = decrypt_field(msg.sender.avatar_url) if (msg.sender and msg.sender.avatar_url) else None
                plain_content = decrypt_field(msg.content) or ""

                results.append(
                    MessageResponse(
                        id=msg.id,
                        sender_id=msg.sender_id,
                        sender_name=s_name,
                        sender_avatar=s_avatar,
                        recipient_id="global",
                        content=plain_content,
                        content_hash=msg.content_hash or compute_hmac_index(plain_content),
                        created_at=msg.created_at,
                        is_edited=msg.is_edited,
                        updated_at=msg.updated_at
                    )
                )
            return results

        can_chat = await ChatService.can_users_chat(session, user_id, recipient_id)
        if not can_chat:
            return []

        try:
            recipient_uuid = UUID(recipient_id)
        except ValueError:
            return []

        u_stmt = select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at == None)
        u_res = await session.execute(u_stmt)
        curr_user = u_res.scalar_one_or_none()
        retention_days = getattr(curr_user, 'chat_retention_days', 180) if curr_user else 180

        chat_conditions = [
            ChatMessageModel.deleted_at == None,
            or_(
                and_(ChatMessageModel.sender_id == user_id, ChatMessageModel.recipient_user_id == recipient_uuid),
                and_(ChatMessageModel.sender_id == recipient_uuid, ChatMessageModel.recipient_user_id == user_id),
                ChatMessageModel.channel_id == recipient_uuid
            )
        ]

        if retention_days > 0:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
            chat_conditions.append(ChatMessageModel.created_at >= cutoff_date)

        stmt = (
            select(ChatMessageModel)
            .options(selectinload(ChatMessageModel.sender))
            .where(and_(*chat_conditions))
            .order_by(ChatMessageModel.created_at.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        docs = res.scalars().all()

        results = []
        for msg in docs:
            s_name = msg.sender.username if msg.sender else "Unknown"
            s_avatar = decrypt_field(msg.sender.avatar_url) if (msg.sender and msg.sender.avatar_url) else None
            plain_content = decrypt_field(msg.content_encrypted) or ""

            results.append(
                MessageResponse(
                    id=msg.id,
                    sender_id=msg.sender_id,
                    sender_name=s_name,
                    sender_avatar=s_avatar,
                    recipient_id=str(msg.channel_id) if msg.channel_id else str(msg.recipient_user_id or recipient_id),
                    content=plain_content,
                    content_hash=msg.content_index or compute_hmac_index(plain_content),
                    created_at=msg.created_at,
                    is_edited=msg.is_edited,
                    updated_at=msg.edited_at
                )
            )
        return results

    @staticmethod
    async def edit_message(session: AsyncSession, sender_id: UUID, message_id: str, new_content: str) -> MessageResponse:
        try:
            msg_uuid = UUID(message_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        gc_stmt = select(GlobalChatMessageModel).options(selectinload(GlobalChatMessageModel.sender)).where(GlobalChatMessageModel.id == msg_uuid)
        gc_res = await session.execute(gc_stmt)
        gc_msg = gc_res.scalar_one_or_none()

        if gc_msg:
            if gc_msg.sender_id != sender_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's message")

            updated_at = datetime.now(timezone.utc)
            enc_content = encrypt_field(new_content)
            c_index = compute_hmac_index(new_content)

            gc_msg.content = enc_content
            gc_msg.content_hash = c_index
            gc_msg.is_edited = True
            gc_msg.updated_at = updated_at

            await session.commit()
            await session.refresh(gc_msg)

            s_name = gc_msg.sender.username if gc_msg.sender else "Unknown"
            s_avatar = decrypt_field(gc_msg.sender.avatar_url) if (gc_msg.sender and gc_msg.sender.avatar_url) else None

            return MessageResponse(
                id=gc_msg.id,
                sender_id=gc_msg.sender_id,
                sender_name=s_name,
                sender_avatar=s_avatar,
                recipient_id="global",
                content=new_content,
                content_hash=c_index,
                created_at=gc_msg.created_at,
                is_edited=gc_msg.is_edited,
                updated_at=gc_msg.updated_at
            )

        stmt = select(ChatMessageModel).options(selectinload(ChatMessageModel.sender)).where(ChatMessageModel.id == msg_uuid, ChatMessageModel.deleted_at == None)
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg.sender_id != sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's message")

        updated_at = datetime.now(timezone.utc)
        enc_content = encrypt_field(new_content)
        c_index = compute_hmac_index(new_content)

        msg.content_encrypted = enc_content
        msg.content_index = c_index
        msg.is_edited = True
        msg.edited_at = updated_at

        await session.commit()
        await session.refresh(msg)

        s_name = msg.sender.username if msg.sender else "Unknown"
        s_avatar = decrypt_field(msg.sender.avatar_url) if (msg.sender and msg.sender.avatar_url) else None

        return MessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=s_name,
            sender_avatar=s_avatar,
            recipient_id=str(msg.channel_id) if msg.channel_id else str(msg.recipient_user_id),
            content=new_content,
            content_hash=c_index,
            created_at=msg.created_at,
            is_edited=msg.is_edited,
            updated_at=msg.edited_at
        )

    @staticmethod
    async def delete_message(session: AsyncSession, sender_id: UUID, message_id: str) -> dict:
        try:
            msg_uuid = UUID(message_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        gc_stmt = select(GlobalChatMessageModel).where(GlobalChatMessageModel.id == msg_uuid)
        gc_res = await session.execute(gc_stmt)
        gc_msg = gc_res.scalar_one_or_none()

        if gc_msg:
            if gc_msg.sender_id != sender_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete someone else's message")
            await session.delete(gc_msg)
            await session.commit()
            return {"message": "Message deleted successfully", "recipient_id": "global"}

        stmt = select(ChatMessageModel).where(ChatMessageModel.id == msg_uuid, ChatMessageModel.deleted_at == None)
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg.sender_id != sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete someone else's message")

        rec_id = str(msg.channel_id) if msg.channel_id else str(msg.recipient_user_id)
        msg.deleted_at = datetime.now(timezone.utc)
        await session.commit()
        return {"message": "Message deleted successfully", "recipient_id": rec_id}

    @staticmethod
    async def get_chat_users(session: AsyncSession, current_user_id: UUID) -> list[ChatUser]:
        u_stmt = (
            select(UserModel)
            .where(
                and_(
                    UserModel.id != current_user_id,
                    UserModel.deleted_at == None
                )
            )
            .order_by(UserModel.username)
        )
        u_res = await session.execute(u_stmt)
        users = u_res.scalars().all()

        if not users:
            return []

        req_stmt = select(ChatRequestModel).where(
            or_(
                ChatRequestModel.requester_id == current_user_id,
                ChatRequestModel.recipient_id == current_user_id
            )
        )
        req_res = await session.execute(req_stmt)
        requests = req_res.scalars().all()

        req_map: dict[UUID, ChatRequestModel] = {}
        for r in requests:
            other_id = r.recipient_id if r.requester_id == current_user_id else r.requester_id
            req_map[other_id] = r

        results = []
        for u in users:
            req = req_map.get(u.id)
            if not req:
                conn_status = "none"
            else:
                req_status = _str(req.status).lower()
                if req_status == "accepted":
                    conn_status = "accepted"
                elif req_status == "declined":
                    conn_status = "declined"
                elif req_status == "pending":
                    if req.requester_id == current_user_id:
                        conn_status = "pending_sent"
                    else:
                        conn_status = "pending_received"
                else:
                    conn_status = "none"

            results.append(
                ChatUser(
                    id=u.id,
                    username=u.username,
                    avatar_url=decrypt_field(u.avatar_url),
                    is_online=connection_manager.is_user_online(str(u.id)),
                    connection_status=conn_status
                )
            )
        return results

    @staticmethod
    async def get_chat_requests(session: AsyncSession, current_user_id: UUID) -> list[ChatRequestResponse]:
        stmt = (
            select(ChatRequestModel)
            .options(
                selectinload(ChatRequestModel.requester),
                selectinload(ChatRequestModel.recipient)
            )
            .where(
                and_(
                    or_(
                        ChatRequestModel.recipient_id == current_user_id,
                        ChatRequestModel.requester_id == current_user_id
                    ),
                    ChatRequestModel.status == "pending"
                )
            )
            .order_by(ChatRequestModel.created_at.desc())
        )
        res = await session.execute(stmt)
        requests = res.scalars().all()

        results = []
        for r in requests:
            req_name = r.requester.username if r.requester else "Unknown"
            req_avatar = decrypt_field(r.requester.avatar_url) if (r.requester and r.requester.avatar_url) else None
            rec_name = r.recipient.username if r.recipient else "Unknown"
            rec_avatar = decrypt_field(r.recipient.avatar_url) if (r.recipient and r.recipient.avatar_url) else None

            results.append(
                ChatRequestResponse(
                    id=r.id,
                    requester_id=r.requester_id,
                    requester_name=req_name,
                    requester_avatar=req_avatar,
                    recipient_id=r.recipient_id,
                    recipient_name=rec_name,
                    recipient_avatar=rec_avatar,
                    status=str(r.status),
                    created_at=r.created_at
                )
            )
        return results

    @staticmethod
    async def send_chat_request(session: AsyncSession, requester_id: UUID, target_identifier: str) -> ChatRequestResponse:
        clean_ident = str(target_identifier).lstrip("@").strip()
        try:
            target_uuid = UUID(clean_ident)
            t_stmt = select(UserModel).where(UserModel.id == target_uuid, UserModel.deleted_at == None)
        except ValueError:
            email_idx = compute_hmac_index(clean_ident.lower())
            t_stmt = select(UserModel).where(
                or_(
                    UserModel.username.ilike(clean_ident),
                    UserModel.email_index == email_idx
                ),
                UserModel.deleted_at == None
            )

        t_res = await session.execute(t_stmt)
        target_user = t_res.scalar_one_or_none()

        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if target_user.id == requester_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot send a chat request to yourself")

        ex_stmt = select(ChatRequestModel).where(
            or_(
                and_(ChatRequestModel.requester_id == requester_id, ChatRequestModel.recipient_id == target_user.id),
                and_(ChatRequestModel.requester_id == target_user.id, ChatRequestModel.recipient_id == requester_id)
            )
        )
        ex_res = await session.execute(ex_stmt)
        ex_req = ex_res.scalar_one_or_none()

        if ex_req:
            if ex_req.status == "accepted":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already chat partners")
            if ex_req.status == "pending":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat request is already pending")

        req_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        new_req = ChatRequestModel(
            id=req_id,
            requester_id=requester_id,
            recipient_id=target_user.id,
            status="pending",
            created_at=now
        )
        session.add(new_req)
        await session.commit()
        await session.refresh(new_req)

        u_stmt = select(UserModel).where(UserModel.id == requester_id)
        u_res = await session.execute(u_stmt)
        requester_user = u_res.scalar_one_or_none()
        requester_name = requester_user.username if requester_user else "Unknown"
        requester_avatar = decrypt_field(requester_user.avatar_url) if (requester_user and requester_user.avatar_url) else None
        target_avatar = decrypt_field(target_user.avatar_url) if target_user.avatar_url else None

        request_resp_data = {
            "id": str(req_id),
            "requester_id": str(requester_id),
            "requester_name": requester_name,
            "requester_avatar": requester_avatar,
            "recipient_id": str(target_user.id),
            "recipient_name": target_user.username,
            "recipient_avatar": target_avatar,
            "status": "pending",
            "created_at": now.isoformat()
        }

        await connection_manager.send_personal_message(
            {
                "type": "chat_request_received",
                "request": request_resp_data
            },
            str(target_user.id)
        )

        return ChatRequestResponse(
            id=req_id,
            requester_id=requester_id,
            requester_name=requester_name,
            requester_avatar=requester_avatar,
            recipient_id=target_user.id,
            recipient_name=target_user.username,
            recipient_avatar=target_avatar,
            status="pending",
            created_at=now
        )

    @staticmethod
    async def respond_chat_request(session: AsyncSession, param1: UUID | str, param2: UUID | str, action: str) -> ChatRequestResponse:
        p1 = str(param1)
        p2 = str(param2)
        try:
            req_uuid = UUID(p1)
            usr_uuid = UUID(p2)
        except ValueError:
            req_uuid = UUID(p2)
            usr_uuid = UUID(p1)

        stmt = (
            select(ChatRequestModel)
            .options(
                selectinload(ChatRequestModel.requester),
                selectinload(ChatRequestModel.recipient)
            )
            .where(
                or_(
                    and_(ChatRequestModel.id == req_uuid, ChatRequestModel.recipient_id == usr_uuid),
                    and_(ChatRequestModel.id == usr_uuid, ChatRequestModel.recipient_id == req_uuid)
                )
            )
        )
        res = await session.execute(stmt)
        req = res.scalar_one_or_none()

        if not req or _str(req.status) != "pending":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat request not found")

        act = action.lower()
        if act in ("decline", "cancel"):
            req.status = "declined"
        elif act == "accept":
            req.status = "accepted"
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")

        await session.commit()
        await session.refresh(req)

        req_name = req.requester.username if req.requester else "Unknown"
        req_avatar = decrypt_field(req.requester.avatar_url) if (req.requester and req.requester.avatar_url) else None
        rec_name = req.recipient.username if req.recipient else "Unknown"
        rec_avatar = decrypt_field(req.recipient.avatar_url) if (req.recipient and req.recipient.avatar_url) else None

        request_resp_data = {
            "id": str(req.id),
            "requester_id": str(req.requester_id),
            "requester_name": req_name,
            "requester_avatar": req_avatar,
            "recipient_id": str(req.recipient_id),
            "recipient_name": rec_name,
            "recipient_avatar": rec_avatar,
            "status": _str(req.status),
            "created_at": req.created_at.isoformat()
        }

        await connection_manager.send_personal_message(
            {
                "type": "chat_request_updated",
                "request": request_resp_data
            },
            str(req.requester_id)
        )
        await connection_manager.send_personal_message(
            {
                "type": "chat_request_updated",
                "request": request_resp_data
            },
            str(req.recipient_id)
        )

        return ChatRequestResponse(
            id=req.id,
            requester_id=req.requester_id,
            requester_name=req_name,
            requester_avatar=req_avatar,
            recipient_id=req.recipient_id,
            recipient_name=rec_name,
            recipient_avatar=rec_avatar,
            status=_str(req.status),
            created_at=req.created_at
        )


chat_service = ChatService()
