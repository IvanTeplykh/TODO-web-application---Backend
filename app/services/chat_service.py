import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload
from app.models.user import UserModel
from app.models.chat import ChatRequestModel, ChatMessageModel
from app.models.global_chat import GlobalChatMessageModel
from app.core.connection_manager import connection_manager
from app.schemas.chat import MessageCreate, MessageResponse, ChatUser, ChatRequestResponse
from app.utils.encryption import encrypt_text, decrypt_text, compute_hash

class ChatService:
    @staticmethod
    async def can_users_chat(session: AsyncSession, user_a: UUID, recipient_id_str: str) -> bool:
        if recipient_id_str == "global":
            return True
        try:
            recipient_uuid = UUID(recipient_id_str)
        except ValueError:
            return False

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
        enc_content = encrypt_text(data.content)
        content_hash = compute_hash(data.content)

        # Fetch sender details from main DB
        sender_stmt = select(UserModel).where(UserModel.id == sender_id)
        sender_res = await session.execute(sender_stmt)
        sender_user = sender_res.scalar_one_or_none()
        sender_name = sender_user.username if sender_user else "Unknown"
        sender_avatar = sender_user.avatar_url if sender_user else None

        if data.recipient_id == "global":
            new_msg = GlobalChatMessageModel(
                id=message_id,
                sender_id=sender_id,
                recipient_id="global",
                encrypted_content=enc_content,
                content_hash=content_hash,
                is_edited=False,
                created_at=created_at,
                updated_at=None
            )
            session.add(new_msg)
            await session.commit()
            await session.refresh(new_msg)
        else:
            new_msg = ChatMessageModel(
                id=message_id,
                sender_id=sender_id,
                recipient_id=data.recipient_id,
                encrypted_content=enc_content,
                content_hash=content_hash,
                is_edited=False,
                created_at=created_at,
                updated_at=None
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
            content_hash=content_hash,
            created_at=created_at,
            is_edited=False,
            updated_at=None
        )

    @staticmethod
    async def get_messages(session: AsyncSession, user_id: UUID, recipient_id: str, limit: int = 100) -> List[MessageResponse]:
        if recipient_id == "global":
            gc_stmt = (
                select(GlobalChatMessageModel)
                .options(selectinload(GlobalChatMessageModel.sender))
                .order_by(GlobalChatMessageModel.created_at.asc())
                .limit(limit)
            )
            gc_res = await session.execute(gc_stmt)
            gc_docs = gc_res.scalars().all()

            results = []
            for msg in gc_docs:
                s_name = msg.sender.username if msg.sender else "Unknown"
                s_avatar = msg.sender.avatar_url if msg.sender else None
                plain_content = decrypt_text(msg.encrypted_content) or ""

                results.append(
                    MessageResponse(
                        id=msg.id,
                        sender_id=msg.sender_id,
                        sender_name=s_name,
                        sender_avatar=s_avatar,
                        recipient_id="global",
                        content=plain_content,
                        content_hash=msg.content_hash,
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

        str_recipient_id = str(recipient_uuid)

        stmt = (
            select(ChatMessageModel)
            .options(selectinload(ChatMessageModel.sender))
            .where(
                or_(
                    and_(ChatMessageModel.sender_id == user_id, ChatMessageModel.recipient_id == str_recipient_id),
                    and_(ChatMessageModel.sender_id == recipient_uuid, ChatMessageModel.recipient_id == str(user_id))
                )
            )
            .order_by(ChatMessageModel.created_at.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        docs = res.scalars().all()

        results = []
        for msg in docs:
            s_name = msg.sender.username if msg.sender else "Unknown"
            s_avatar = msg.sender.avatar_url if msg.sender else None
            plain_content = decrypt_text(msg.encrypted_content) or ""

            results.append(
                MessageResponse(
                    id=msg.id,
                    sender_id=msg.sender_id,
                    sender_name=s_name,
                    sender_avatar=s_avatar,
                    recipient_id=msg.recipient_id,
                    content=plain_content,
                    content_hash=msg.content_hash,
                    created_at=msg.created_at,
                    is_edited=msg.is_edited,
                    updated_at=msg.updated_at
                )
            )
        return results

    @staticmethod
    async def edit_message(session: AsyncSession, sender_id: UUID, message_id: str, new_content: str) -> MessageResponse:
        try:
            msg_uuid = UUID(message_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        # Check global chat messages first
        gc_stmt = select(GlobalChatMessageModel).options(selectinload(GlobalChatMessageModel.sender)).where(GlobalChatMessageModel.id == msg_uuid)
        gc_res = await session.execute(gc_stmt)
        gc_msg = gc_res.scalar_one_or_none()

        if gc_msg:
            if gc_msg.sender_id != sender_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's message")

            updated_at = datetime.now(timezone.utc)
            enc_content = encrypt_text(new_content)
            c_hash = compute_hash(new_content)

            gc_msg.encrypted_content = enc_content
            gc_msg.content_hash = c_hash
            gc_msg.is_edited = True
            gc_msg.updated_at = updated_at

            await session.commit()
            await session.refresh(gc_msg)

            s_name = gc_msg.sender.username if gc_msg.sender else "Unknown"
            s_avatar = gc_msg.sender.avatar_url if gc_msg.sender else None

            return MessageResponse(
                id=gc_msg.id,
                sender_id=gc_msg.sender_id,
                sender_name=s_name,
                sender_avatar=s_avatar,
                recipient_id="global",
                content=new_content,
                content_hash=c_hash,
                created_at=gc_msg.created_at,
                is_edited=gc_msg.is_edited,
                updated_at=gc_msg.updated_at
            )

        # Fallback to private chat DB
        stmt = select(ChatMessageModel).options(selectinload(ChatMessageModel.sender)).where(ChatMessageModel.id == msg_uuid)
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg.sender_id != sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's message")

        updated_at = datetime.now(timezone.utc)
        enc_content = encrypt_text(new_content)
        c_hash = compute_hash(new_content)
        
        msg.encrypted_content = enc_content
        msg.content_hash = c_hash
        msg.is_edited = True
        msg.updated_at = updated_at

        await session.commit()
        await session.refresh(msg)

        s_name = msg.sender.username if msg.sender else "Unknown"
        s_avatar = msg.sender.avatar_url if msg.sender else None

        return MessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=s_name,
            sender_avatar=s_avatar,
            recipient_id=msg.recipient_id,
            content=new_content,
            content_hash=c_hash,
            created_at=msg.created_at,
            is_edited=msg.is_edited,
            updated_at=msg.updated_at
        )

    @staticmethod
    async def delete_message(session: AsyncSession, sender_id: UUID, message_id: str) -> dict:
        try:
            msg_uuid = UUID(message_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        # Check global chat messages first
        gc_stmt = select(GlobalChatMessageModel).where(GlobalChatMessageModel.id == msg_uuid)
        gc_res = await session.execute(gc_stmt)
        gc_msg = gc_res.scalar_one_or_none()

        if gc_msg:
            if gc_msg.sender_id != sender_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete someone else's message")

            deleted_info = {
                "message_id": str(gc_msg.id),
                "recipient_id": "global",
                "sender_id": str(gc_msg.sender_id)
            }

            await session.delete(gc_msg)
            await session.commit()
            return deleted_info

        # Fallback to private chat DB
        stmt = select(ChatMessageModel).where(ChatMessageModel.id == msg_uuid)
        res = await session.execute(stmt)
        msg = res.scalar_one_or_none()

        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg.sender_id != sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete someone else's message")

        deleted_info = {
            "message_id": str(msg.id),
            "recipient_id": msg.recipient_id,
            "sender_id": str(msg.sender_id)
        }

        await session.delete(msg)
        await session.commit()
        return deleted_info

    @staticmethod
    async def get_chat_users(session: AsyncSession, current_user_id: UUID) -> List[ChatUser]:
        stmt = select(UserModel).where(UserModel.id != current_user_id)
        res = await session.execute(stmt)
        users = res.scalars().all()

        req_stmt = select(ChatRequestModel).where(
            or_(ChatRequestModel.requester_id == current_user_id, ChatRequestModel.recipient_id == current_user_id)
        )
        req_res = await session.execute(req_stmt)
        requests = req_res.scalars().all()

        status_map = {}
        for r in requests:
            other_id = r.recipient_id if r.requester_id == current_user_id else r.requester_id
            if r.status == "accepted":
                status_map[other_id] = "accepted"
            elif r.status == "pending":
                if r.requester_id == current_user_id:
                    status_map[other_id] = "pending_sent"
                else:
                    status_map[other_id] = "pending_received"

        result_users = []
        for u in users:
            result_users.append(
                ChatUser(
                    id=u.id,
                    username=u.username,
                    email=u.email,
                    avatar_url=u.avatar_url,
                    is_online=connection_manager.is_user_online(str(u.id)),
                    connection_status=status_map.get(u.id, "none")
                )
            )
        return result_users

    @staticmethod
    async def send_chat_request(session: AsyncSession, requester_id: UUID, recipient_id_str: str) -> ChatRequestResponse:
        try:
            recipient_uuid = UUID(recipient_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient user not found")

        if requester_id == recipient_uuid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot send chat request to yourself")

        recipient_user_stmt = select(UserModel).where(UserModel.id == recipient_uuid)
        res1 = await session.execute(recipient_user_stmt)
        recipient_user = res1.scalar_one_or_none()
        if not recipient_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient user not found")

        requester_user_stmt = select(UserModel).where(UserModel.id == requester_id)
        res2 = await session.execute(requester_user_stmt)
        requester_user = res2.scalar_one_or_none()

        existing_stmt = select(ChatRequestModel).where(
            or_(
                and_(ChatRequestModel.requester_id == requester_id, ChatRequestModel.recipient_id == recipient_uuid),
                and_(ChatRequestModel.requester_id == recipient_uuid, ChatRequestModel.recipient_id == requester_id)
            )
        )
        ex_res = await session.execute(existing_stmt)
        existing = ex_res.scalar_one_or_none()

        if existing:
            if existing.status == "accepted":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat connection already accepted")
            elif existing.status == "pending":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat request already pending")
            else:
                existing.requester_id = requester_id
                existing.recipient_id = recipient_uuid
                existing.status = "pending"
                existing.created_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(existing)
                return ChatRequestResponse(
                    id=existing.id,
                    requester_id=requester_id,
                    requester_name=requester_user.username,
                    requester_avatar=requester_user.avatar_url,
                    recipient_id=recipient_uuid,
                    recipient_name=recipient_user.username,
                    recipient_avatar=recipient_user.avatar_url,
                    status="pending",
                    created_at=existing.created_at
                )

        new_req = ChatRequestModel(
            id=uuid.uuid4(),
            requester_id=requester_id,
            recipient_id=recipient_uuid,
            status="pending",
            created_at=datetime.now(timezone.utc)
        )
        session.add(new_req)
        await session.commit()
        await session.refresh(new_req)

        return ChatRequestResponse(
            id=new_req.id,
            requester_id=requester_id,
            requester_name=requester_user.username,
            requester_avatar=requester_user.avatar_url,
            recipient_id=recipient_uuid,
            recipient_name=recipient_user.username,
            recipient_avatar=recipient_user.avatar_url,
            status="pending",
            created_at=new_req.created_at
        )

    @staticmethod
    async def respond_chat_request(session: AsyncSession, user_id: UUID, request_id: str, action: str) -> ChatRequestResponse:
        try:
            req_uuid = UUID(request_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat request not found")

        stmt = select(ChatRequestModel).options(
            selectinload(ChatRequestModel.requester),
            selectinload(ChatRequestModel.recipient)
        ).where(ChatRequestModel.id == req_uuid)
        res = await session.execute(stmt)
        req_doc = res.scalar_one_or_none()

        if not req_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat request not found")

        if req_doc.recipient_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only request recipient can respond")

        req_doc.status = "accepted" if action == "accept" else "declined"
        await session.commit()
        await session.refresh(req_doc)

        req_name = req_doc.requester.username if req_doc.requester else "Unknown"
        req_avatar = req_doc.requester.avatar_url if req_doc.requester else None
        rec_name = req_doc.recipient.username if req_doc.recipient else "Unknown"
        rec_avatar = req_doc.recipient.avatar_url if req_doc.recipient else None

        return ChatRequestResponse(
            id=req_doc.id,
            requester_id=req_doc.requester_id,
            requester_name=req_name,
            requester_avatar=req_avatar,
            recipient_id=req_doc.recipient_id,
            recipient_name=rec_name,
            recipient_avatar=rec_avatar,
            status=req_doc.status,
            created_at=req_doc.created_at
        )

    @staticmethod
    async def get_chat_requests(session: AsyncSession, user_id: UUID) -> List[ChatRequestResponse]:
        stmt = (
            select(ChatRequestModel)
            .options(
                selectinload(ChatRequestModel.requester),
                selectinload(ChatRequestModel.recipient)
            )
            .where(or_(ChatRequestModel.requester_id == user_id, ChatRequestModel.recipient_id == user_id))
        )
        res = await session.execute(stmt)
        docs = res.scalars().all()

        results = []
        for r in docs:
            req_name = r.requester.username if r.requester else "Unknown"
            req_avatar = r.requester.avatar_url if r.requester else None
            rec_name = r.recipient.username if r.recipient else "Unknown"
            rec_avatar = r.recipient.avatar_url if r.recipient else None

            results.append(
                ChatRequestResponse(
                    id=r.id,
                    requester_id=r.requester_id,
                    requester_name=req_name,
                    requester_avatar=req_avatar,
                    recipient_id=r.recipient_id,
                    recipient_name=rec_name,
                    recipient_avatar=rec_avatar,
                    status=r.status,
                    created_at=r.created_at
                )
            )
        return results

chat_service = ChatService()
