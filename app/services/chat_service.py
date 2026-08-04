import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from app.core.database import db
from app.core.connection_manager import connection_manager
from app.schemas.chat import MessageCreate, MessageResponse, ChatUser, ChatRequestResponse

class ChatService:
    @staticmethod
    async def can_users_chat(user_a: str, user_b: str) -> bool:
        if user_b == "global":
            return True
        doc = await db.chat_requests_collection.find_one({
            "$or": [
                {"requester_id": user_a, "recipient_id": user_b, "status": "accepted"},
                {"requester_id": user_b, "recipient_id": user_a, "status": "accepted"}
            ]
        })
        return doc is not None

    @staticmethod
    async def create_message(
        sender_id: UUID,
        sender_name: str,
        sender_avatar: Optional[str],
        data: MessageCreate
    ) -> MessageResponse:
        message_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(data.content.encode("utf-8")).hexdigest()
        
        doc = {
            "_id": message_id,
            "sender_id": str(sender_id),
            "sender_name": sender_name,
            "sender_avatar": sender_avatar,
            "recipient_id": data.recipient_id,
            "content": data.content,
            "content_hash": content_hash,
            "created_at": created_at.isoformat(),
            "is_edited": False,
            "updated_at": None
        }
        
        await db.messages_collection.insert_one(doc)
        
        return MessageResponse(
            id=UUID(message_id),
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
    async def get_messages(user_id: UUID, recipient_id: str, limit: int = 100) -> List[MessageResponse]:
        str_user_id = str(user_id)
        
        if recipient_id == "global":
            query = {"recipient_id": "global"}
        else:
            # Check if chat is allowed
            can_chat = await ChatService.can_users_chat(str_user_id, recipient_id)
            if not can_chat:
                return []

            query = {
                "$or": [
                    {"sender_id": str_user_id, "recipient_id": recipient_id},
                    {"sender_id": recipient_id, "recipient_id": str_user_id}
                ]
            }
            
        cursor = db.messages_collection.find(query).sort("created_at", 1).limit(limit)
        docs = await cursor.to_list(length=limit)

        # Batch lookup latest user profile details (username & avatar) for all message senders
        sender_ids = list({d["sender_id"] for d in docs if "sender_id" in d})
        senders_map = {}
        if sender_ids:
            senders_cursor = db.users_collection.find({"_id": {"$in": sender_ids}})
            senders_list = await senders_cursor.to_list(length=len(sender_ids))
            senders_map = {str(u["_id"]): u for u in senders_list}
        
        results = []
        for d in docs:
            created_dt = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
            updated_dt = datetime.fromisoformat(d["updated_at"]) if d.get("updated_at") else None
            
            sender_user = senders_map.get(d["sender_id"])
            latest_name = sender_user["username"] if sender_user else d["sender_name"]
            latest_avatar = sender_user.get("avatar_url") if sender_user else d.get("sender_avatar")
            c_hash = d.get("content_hash") or hashlib.sha256(d["content"].encode("utf-8")).hexdigest()

            results.append(
                MessageResponse(
                    id=UUID(d["_id"]),
                    sender_id=UUID(d["sender_id"]),
                    sender_name=latest_name,
                    sender_avatar=latest_avatar,
                    recipient_id=d["recipient_id"],
                    content=d["content"],
                    content_hash=c_hash,
                    created_at=created_dt,
                    is_edited=d.get("is_edited", False),
                    updated_at=updated_dt
                )
            )
        return results

    @staticmethod
    async def edit_message(sender_id: UUID, message_id: str, new_content: str) -> MessageResponse:
        str_sender_id = str(sender_id)
        msg_doc = await db.messages_collection.find_one({"_id": message_id})
        if not msg_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg_doc["sender_id"] != str_sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's message")

        updated_at = datetime.now(timezone.utc)
        c_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        await db.messages_collection.update_one(
            {"_id": message_id},
            {"$set": {
                "content": new_content,
                "content_hash": c_hash,
                "is_edited": True,
                "updated_at": updated_at.isoformat()
            }}
        )

        created_dt = datetime.fromisoformat(msg_doc["created_at"]) if isinstance(msg_doc["created_at"], str) else msg_doc["created_at"]

        return MessageResponse(
            id=UUID(message_id),
            sender_id=sender_id,
            sender_name=msg_doc["sender_name"],
            sender_avatar=msg_doc.get("sender_avatar"),
            recipient_id=msg_doc["recipient_id"],
            content=new_content,
            content_hash=c_hash,
            created_at=created_dt,
            is_edited=True,
            updated_at=updated_at
        )

    @staticmethod
    async def delete_message(sender_id: UUID, message_id: str) -> dict:
        str_sender_id = str(sender_id)
        msg_doc = await db.messages_collection.find_one({"_id": message_id})
        if not msg_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        if msg_doc["sender_id"] != str_sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete someone else's message")

        await db.messages_collection.delete_one({"_id": message_id})
        return {
            "message_id": message_id,
            "recipient_id": msg_doc["recipient_id"],
            "sender_id": msg_doc["sender_id"]
        }

    @staticmethod
    async def get_chat_users(current_user_id: UUID) -> List[ChatUser]:
        str_user_id = str(current_user_id)
        cursor = db.users_collection.find({"_id": {"$ne": str_user_id}})
        docs = await cursor.to_list(length=200)
        
        # Fetch all chat requests for current user to compute connection_status
        req_cursor = db.chat_requests_collection.find({
            "$or": [
                {"requester_id": str_user_id},
                {"recipient_id": str_user_id}
            ]
        })
        requests_docs = await req_cursor.to_list(length=500)
        
        # Map user_id to status
        status_map = {}
        for r in requests_docs:
            other_id = r["recipient_id"] if r["requester_id"] == str_user_id else r["requester_id"]
            if r["status"] == "accepted":
                status_map[other_id] = "accepted"
            elif r["status"] == "pending":
                if r["requester_id"] == str_user_id:
                    status_map[other_id] = "pending_sent"
                else:
                    status_map[other_id] = "pending_received"

        users = []
        for d in docs:
            user_id_str = str(d["_id"])
            users.append(
                ChatUser(
                    id=UUID(user_id_str),
                    username=d["username"],
                    email=d["email"],
                    avatar_url=d.get("avatar_url"),
                    is_online=connection_manager.is_user_online(user_id_str),
                    connection_status=status_map.get(user_id_str, "none")
                )
            )
        return users

    @staticmethod
    async def send_chat_request(requester_id: UUID, recipient_id_str: str) -> ChatRequestResponse:
        str_requester = str(requester_id)
        if str_requester == recipient_id_str:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot send chat request to yourself")

        recipient_user = await db.users_collection.find_one({"_id": recipient_id_str})
        if not recipient_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient user not found")

        requester_user = await db.users_collection.find_one({"_id": str_requester})

        # Check for existing request
        existing = await db.chat_requests_collection.find_one({
            "$or": [
                {"requester_id": str_requester, "recipient_id": recipient_id_str},
                {"requester_id": recipient_id_str, "recipient_id": str_requester}
            ]
        })

        if existing:
            if existing["status"] == "accepted":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat connection already accepted")
            elif existing["status"] == "pending":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat request already pending")
            else:
                # Re-open declined request
                request_id = existing["_id"]
                created_at = datetime.now(timezone.utc)
                await db.chat_requests_collection.update_one(
                    {"_id": request_id},
                    {"$set": {
                        "requester_id": str_requester,
                        "recipient_id": recipient_id_str,
                        "status": "pending",
                        "created_at": created_at.isoformat()
                    }}
                )
                return ChatRequestResponse(
                    id=UUID(request_id),
                    requester_id=requester_id,
                    requester_name=requester_user["username"],
                    requester_avatar=requester_user.get("avatar_url"),
                    recipient_id=UUID(recipient_id_str),
                    recipient_name=recipient_user["username"],
                    recipient_avatar=recipient_user.get("avatar_url"),
                    status="pending",
                    created_at=created_at
                )

        request_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        
        doc = {
            "_id": request_id,
            "requester_id": str_requester,
            "recipient_id": recipient_id_str,
            "status": "pending",
            "created_at": created_at.isoformat()
        }
        await db.chat_requests_collection.insert_one(doc)

        return ChatRequestResponse(
            id=UUID(request_id),
            requester_id=requester_id,
            requester_name=requester_user["username"],
            requester_avatar=requester_user.get("avatar_url"),
            recipient_id=UUID(recipient_id_str),
            recipient_name=recipient_user["username"],
            recipient_avatar=recipient_user.get("avatar_url"),
            status="pending",
            created_at=created_at
        )

    @staticmethod
    async def respond_chat_request(user_id: UUID, request_id: str, action: str) -> ChatRequestResponse:
        str_user_id = str(user_id)
        request_doc = await db.chat_requests_collection.find_one({"_id": request_id})
        if not request_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat request not found")

        if request_doc["recipient_id"] != str_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only request recipient can respond")

        new_status = "accepted" if action == "accept" else "declined"
        await db.chat_requests_collection.update_one(
            {"_id": request_id},
            {"$set": {"status": new_status}}
        )

        requester_user = await db.users_collection.find_one({"_id": request_doc["requester_id"]})
        recipient_user = await db.users_collection.find_one({"_id": request_doc["recipient_id"]})

        created_dt = datetime.fromisoformat(request_doc["created_at"]) if isinstance(request_doc["created_at"], str) else request_doc["created_at"]

        return ChatRequestResponse(
            id=UUID(request_id),
            requester_id=UUID(request_doc["requester_id"]),
            requester_name=requester_user["username"] if requester_user else "Unknown",
            requester_avatar=requester_user.get("avatar_url") if requester_user else None,
            recipient_id=UUID(request_doc["recipient_id"]),
            recipient_name=recipient_user["username"] if recipient_user else "Unknown",
            recipient_avatar=recipient_user.get("avatar_url") if recipient_user else None,
            status=new_status,
            created_at=created_dt
        )

    @staticmethod
    async def get_chat_requests(user_id: UUID) -> List[ChatRequestResponse]:
        str_user_id = str(user_id)
        cursor = db.chat_requests_collection.find({
            "$or": [
                {"requester_id": str_user_id},
                {"recipient_id": str_user_id}
            ]
        })
        docs = await cursor.to_list(length=500)

        user_ids = set()
        for d in docs:
            user_ids.add(d["requester_id"])
            user_ids.add(d["recipient_id"])

        users_cursor = db.users_collection.find({"_id": {"$in": list(user_ids)}})
        users_docs = await users_cursor.to_list(length=len(user_ids))
        users_map = {str(u["_id"]): u for u in users_docs}

        results = []
        for d in docs:
            req_u = users_map.get(d["requester_id"], {})
            rec_u = users_map.get(d["recipient_id"], {})
            created_dt = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
            results.append(
                ChatRequestResponse(
                    id=UUID(d["_id"]),
                    requester_id=UUID(d["requester_id"]),
                    requester_name=req_u.get("username", "Unknown"),
                    requester_avatar=req_u.get("avatar_url"),
                    recipient_id=UUID(d["recipient_id"]),
                    recipient_name=rec_u.get("username", "Unknown"),
                    recipient_avatar=rec_u.get("avatar_url"),
                    status=d["status"],
                    created_at=created_dt
                )
            )
        return results

chat_service = ChatService()
