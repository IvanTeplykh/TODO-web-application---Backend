import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from app.core.database import db
from app.core.connection_manager import connection_manager
from app.schemas.chat import MessageCreate, MessageResponse, ChatUser

class ChatService:
    @staticmethod
    async def create_message(
        sender_id: UUID,
        sender_name: str,
        sender_avatar: Optional[str],
        data: MessageCreate
    ) -> MessageResponse:
        message_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        
        doc = {
            "_id": message_id,
            "sender_id": str(sender_id),
            "sender_name": sender_name,
            "sender_avatar": sender_avatar,
            "recipient_id": data.recipient_id,
            "content": data.content,
            "created_at": created_at.isoformat()
        }
        
        await db.database["messages"].insert_one(doc)
        
        return MessageResponse(
            id=UUID(message_id),
            sender_id=sender_id,
            sender_name=sender_name,
            sender_avatar=sender_avatar,
            recipient_id=data.recipient_id,
            content=data.content,
            created_at=created_at
        )

    @staticmethod
    async def get_messages(user_id: UUID, recipient_id: str, limit: int = 100) -> List[MessageResponse]:
        str_user_id = str(user_id)
        
        if recipient_id == "global":
            query = {"recipient_id": "global"}
        else:
            query = {
                "$or": [
                    {"sender_id": str_user_id, "recipient_id": recipient_id},
                    {"sender_id": recipient_id, "recipient_id": str_user_id}
                ]
            }
            
        cursor = db.database["messages"].find(query).sort("created_at", 1).limit(limit)
        docs = await cursor.to_list(length=limit)
        
        results = []
        for d in docs:
            created_dt = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
            results.append(
                MessageResponse(
                    id=UUID(d["_id"]),
                    sender_id=UUID(d["sender_id"]),
                    sender_name=d["sender_name"],
                    sender_avatar=d.get("sender_avatar"),
                    recipient_id=d["recipient_id"],
                    content=d["content"],
                    created_at=created_dt
                )
            )
        return results

    @staticmethod
    async def get_chat_users(current_user_id: UUID) -> List[ChatUser]:
        cursor = db.users_collection.find({"_id": {"$ne": str(current_user_id)}})
        docs = await cursor.to_list(length=200)
        
        users = []
        for d in docs:
            user_id_str = str(d["_id"])
            users.append(
                ChatUser(
                    id=UUID(user_id_str),
                    username=d["username"],
                    email=d["email"],
                    avatar_url=d.get("avatar_url"),
                    is_online=connection_manager.is_user_online(user_id_str)
                )
            )
        return users

chat_service = ChatService()
