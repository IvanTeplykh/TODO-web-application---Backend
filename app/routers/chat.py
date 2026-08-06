from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.connection_manager import connection_manager
from app.core.database import db, get_db
from app.dependencies.auth import get_current_user
from app.models.channel import ChannelModel
from app.models.user import UserModel
from app.schemas.chat import (
    ChatRequestAction,
    ChatRequestCreate,
    ChatRequestResponse,
    ChatUser,
    MessageCreate,
    MessageResponse,
    MessageUpdate,
)
from app.schemas.user import UserResponse
from app.services.channel_service import channel_service
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

async def get_user_from_token_string(session: AsyncSession, token: str) -> UserResponse:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Invalid token sub")
        user_uuid = UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid WebSocket authentication token"
        )
        
    stmt = select(UserModel).where(UserModel.id == user_uuid)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
        
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url
    )

@router.get("/users", response_model=list[ChatUser])
async def get_chat_users(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await chat_service.get_chat_users(session, current_user.id)

@router.get("/messages", response_model=list[MessageResponse])
async def get_chat_messages(
    recipient_id: str = Query("global", description="Recipient UUID or 'global'"),
    limit: int = Query(100, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await chat_service.get_messages(session, current_user.id, recipient_id, limit)

@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_message(
    data: MessageCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    can_chat = await chat_service.can_users_chat(session, current_user.id, data.recipient_id)
    if not can_chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private chat request must be accepted before sending messages"
        )
    res = await chat_service.create_message(session, current_user.id, data)
    payload = {
        "type": "new_message",
        "message": {
            "id": str(res.id),
            "sender_id": str(res.sender_id),
            "sender_name": res.sender_name,
            "sender_avatar": res.sender_avatar,
            "recipient_id": res.recipient_id,
            "content": res.content,
            "content_hash": res.content_hash,
            "created_at": res.created_at.isoformat(),
            "is_edited": False,
            "updated_at": None
        }
    }
    if data.recipient_id == "global":
        await connection_manager.broadcast(payload)
    else:
        await connection_manager.send_personal_message(payload, data.recipient_id)
        if data.recipient_id.lower() != str(current_user.id).lower():
            await connection_manager.send_personal_message(payload, str(current_user.id))
    return res

@router.patch("/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: str,
    data: MessageUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await chat_service.edit_message(session, current_user.id, message_id, data.content)
    
    payload = {
        "type": "message_edited",
        "message": {
            "id": str(res.id),
            "sender_id": str(res.sender_id),
            "sender_name": res.sender_name,
            "sender_avatar": res.sender_avatar,
            "recipient_id": res.recipient_id,
            "content": res.content,
            "content_hash": res.content_hash,
            "created_at": res.created_at.isoformat(),
            "is_edited": res.is_edited,
            "updated_at": res.updated_at.isoformat() if res.updated_at else None
        }
    }
    
    if res.recipient_id == "global":
        await connection_manager.broadcast(payload)
    else:
        await connection_manager.send_personal_message(payload, res.recipient_id)
        if res.recipient_id != str(res.sender_id):
            await connection_manager.send_personal_message(payload, str(res.sender_id))
            
    return res

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await chat_service.delete_message(session, current_user.id, message_id)
    
    payload = {
        "type": "message_deleted",
        "message_id": message_id,
        "recipient_id": res["recipient_id"]
    }
    
    if res["recipient_id"] == "global":
        await connection_manager.broadcast(payload)
    else:
        await connection_manager.send_personal_message(payload, res["recipient_id"])
        if res["recipient_id"] != res["sender_id"]:
            await connection_manager.send_personal_message(payload, res["sender_id"])
            
    return {"message": "Message deleted successfully", "id": message_id}

@router.post("/requests", response_model=ChatRequestResponse, status_code=status.HTTP_201_CREATED)
async def send_chat_request(
    data: ChatRequestCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await chat_service.send_chat_request(session, current_user.id, data.recipient_id)
    
    payload = {
        "type": "chat_request_received",
        "request": res.model_dump(mode="json")
    }
    await connection_manager.send_personal_message(payload, data.recipient_id)
    await connection_manager.send_personal_message(payload, str(current_user.id))
    
    return res

@router.get("/requests", response_model=list[ChatRequestResponse])
async def get_chat_requests(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await chat_service.get_chat_requests(session, current_user.id)

@router.patch("/requests/{request_id}", response_model=ChatRequestResponse)
async def respond_chat_request(
    request_id: str,
    data: ChatRequestAction,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    res = await chat_service.respond_chat_request(session, current_user.id, request_id, data.action)
    
    update_payload = {
        "type": "chat_request_updated",
        "request": res.model_dump(mode="json")
    }
    await connection_manager.send_personal_message(update_payload, str(res.requester_id))
    await connection_manager.send_personal_message(update_payload, str(res.recipient_id))
    
    return res

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(None)):
    # 1. Accept WebSocket handshake first to establish WS protocol (prevents HTTP 500 on close)
    await websocket.accept()

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    clean_token = token.strip('"\'')

    async with db.session_factory() as session:
        try:
            current_user = await get_user_from_token_string(session, clean_token)
        except Exception as e:
            print(f"[WS AUTH ERROR] Invalid token: {e}")
            try:
                await websocket.send_json({"type": "error", "detail": "Invalid authentication token"})
            except Exception:
                pass
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    user_id_str = str(current_user.id).lower()
    connection_manager.connect(user_id_str, websocket)

    online_ids = [uid for uid, conns in connection_manager.active_connections.items() if conns]
    print(f"[WS CONNECTED] User @{current_user.username} ({user_id_str}) connected. Active online users: {online_ids}")

    # 1. Send currently connected online users to the new client
    await websocket.send_json({
        "type": "online_users",
        "user_ids": online_ids
    })

    # 2. Notify connected users that someone came online
    await connection_manager.broadcast({
        "type": "user_status",
        "user_id": user_id_str,
        "is_online": True
    })

    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle client ping messages on the server
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            recipient_id = data.get("recipient_id", "global")
            content = data.get("content", "").strip()

            if not content:
                continue

            async with db.session_factory() as session:
                can_chat = await chat_service.can_users_chat(session, current_user.id, recipient_id)
                if not can_chat:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "Private chat request must be accepted before sending messages"
                    })
                    continue

                try:
                    rec_uuid = UUID(recipient_id)
                except ValueError:
                    rec_uuid = None

                is_channel = False
                if rec_uuid:
                    ch_stmt = select(ChannelModel).where(ChannelModel.id == rec_uuid)
                    ch_res = await session.execute(ch_stmt)
                    is_channel = ch_res.scalar_one_or_none() is not None

                if is_channel and rec_uuid:
                    saved_chan_msg = await channel_service.create_channel_message(
                        session=session,
                        channel_id=rec_uuid,
                        sender_id=current_user.id,
                        content=content
                    )
                    msg_payload = {
                        "type": "new_channel_message",
                        "message": saved_chan_msg.model_dump(mode="json")
                    }
                    await connection_manager.broadcast(msg_payload)
                    continue

                msg_in = MessageCreate(recipient_id=recipient_id, content=content)
                saved_msg = await chat_service.create_message(
                    session=session,
                    sender_id=current_user.id,
                    data=msg_in
                )

            msg_payload = {
                "type": "new_message",
                "message": {
                    "id": str(saved_msg.id),
                    "sender_id": str(saved_msg.sender_id),
                    "sender_name": saved_msg.sender_name,
                    "sender_avatar": saved_msg.sender_avatar,
                    "recipient_id": saved_msg.recipient_id,
                    "content": saved_msg.content,
                    "content_hash": saved_msg.content_hash,
                    "created_at": saved_msg.created_at.isoformat(),
                    "is_edited": False,
                    "updated_at": None
                }
            }

            if recipient_id == "global":
                await connection_manager.broadcast(msg_payload)
            else:
                await connection_manager.send_personal_message(msg_payload, recipient_id)
                if recipient_id != user_id_str:
                    await connection_manager.send_personal_message(msg_payload, user_id_str)

    except Exception as e:
        # Log receive loop error instead of silent failure
        print(f"[WS ERROR] Connection error for user {user_id_str}: {e}")
    finally:
        connection_manager.disconnect(user_id_str, websocket)
        if not connection_manager.is_user_online(user_id_str):
            await connection_manager.broadcast({
                "type": "user_status",
                "user_id": user_id_str,
                "is_online": False
            })
