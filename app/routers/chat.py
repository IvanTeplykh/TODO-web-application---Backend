from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, HTTPException, status
from typing import List, Optional
from uuid import UUID
from jose import jwt, JWTError
from app.core.config import settings
from app.core.database import db
from app.core.connection_manager import connection_manager
from app.dependencies.auth import get_current_user
from app.schemas.chat import (
    MessageCreate,
    MessageResponse,
    ChatUser,
    ChatRequestCreate,
    ChatRequestAction,
    ChatRequestResponse
)
from app.schemas.user import UserResponse
from app.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

async def get_user_from_token_string(token: str) -> UserResponse:
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
        
    user = await db.users_collection.find_one({"_id": str(user_uuid)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
        
    return UserResponse(
        id=UUID(user["_id"]),
        username=user["username"],
        email=user["email"],
        avatar_url=user.get("avatar_url")
    )

@router.get("/users", response_model=List[ChatUser])
async def get_chat_users(current_user: UserResponse = Depends(get_current_user)):
    return await chat_service.get_chat_users(current_user.id)

@router.get("/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    recipient_id: str = Query("global", description="Recipient UUID or 'global'"),
    limit: int = Query(100, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user)
):
    return await chat_service.get_messages(current_user.id, recipient_id, limit)

@router.post("/requests", response_model=ChatRequestResponse, status_code=status.HTTP_201_CREATED)
async def send_chat_request(
    data: ChatRequestCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    res = await chat_service.send_chat_request(current_user.id, data.recipient_id)
    
    # Broadcast real-time notification to recipient
    await connection_manager.send_personal_message({
        "type": "chat_request_received",
        "request": res.model_dump(mode="json")
    }, data.recipient_id)
    
    return res

@router.get("/requests", response_model=List[ChatRequestResponse])
async def get_chat_requests(current_user: UserResponse = Depends(get_current_user)):
    return await chat_service.get_chat_requests(current_user.id)

@router.patch("/requests/{request_id}", response_model=ChatRequestResponse)
async def respond_chat_request(
    request_id: str,
    data: ChatRequestAction,
    current_user: UserResponse = Depends(get_current_user)
):
    res = await chat_service.respond_chat_request(current_user.id, request_id, data.action)
    
    # Broadcast real-time update to both requester and recipient
    update_payload = {
        "type": "chat_request_updated",
        "request": res.model_dump(mode="json")
    }
    await connection_manager.send_personal_message(update_payload, str(res.requester_id))
    await connection_manager.send_personal_message(update_payload, str(res.recipient_id))
    
    return res

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    try:
        current_user = await get_user_from_token_string(token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id_str = str(current_user.id)
    await connection_manager.connect(user_id_str, websocket)

    # Notify connected users that someone came online
    await connection_manager.broadcast({
        "type": "user_status",
        "user_id": user_id_str,
        "is_online": True
    })

    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle ping/pong heartbeat to keep connection alive on cloud platforms
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            recipient_id = data.get("recipient_id", "global")
            content = data.get("content", "").strip()

            if not content:
                continue

            # Verify that private chat connection is accepted before sending message
            can_chat = await chat_service.can_users_chat(user_id_str, recipient_id)
            if not can_chat:
                await websocket.send_json({
                    "type": "error",
                    "detail": "Private chat request must be accepted before sending messages"
                })
                continue

            msg_in = MessageCreate(recipient_id=recipient_id, content=content)
            saved_msg = await chat_service.create_message(
                sender_id=current_user.id,
                sender_name=current_user.username,
                sender_avatar=current_user.avatar_url,
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
                    "created_at": saved_msg.created_at.isoformat()
                }
            }

            if recipient_id == "global":
                await connection_manager.broadcast(msg_payload)
            else:
                # Send to recipient and echo back to sender
                await connection_manager.send_personal_message(msg_payload, recipient_id)
                if recipient_id != user_id_str:
                    await connection_manager.send_personal_message(msg_payload, user_id_str)

    except WebSocketDisconnect:
        connection_manager.disconnect(user_id_str, websocket)
        if not connection_manager.is_user_online(user_id_str):
            await connection_manager.broadcast({
                "type": "user_status",
                "user_id": user_id_str,
                "is_online": False
            })
