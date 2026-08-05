from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID

class ChatUser(BaseModel):
    id: UUID
    username: str
    avatar_url: Optional[str] = None
    is_online: bool = False
    connection_status: Optional[str] = Field("none", description="accepted, pending_sent, pending_received, none")

class MessageCreate(BaseModel):
    recipient_id: str = Field(..., description="UUID of recipient user or 'global'")
    content: str = Field(..., min_length=1, max_length=2000, description="Message text content")

class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="New message text content")

class MessageResponse(BaseModel):
    id: UUID
    sender_id: UUID
    sender_name: str
    sender_avatar: Optional[str] = None
    recipient_id: str
    content: str
    content_hash: Optional[str] = Field(None, description="SHA-256 integrity hash of content")
    created_at: datetime
    is_edited: bool = False
    updated_at: Optional[datetime] = None

class ChatRequestCreate(BaseModel):
    recipient_id: str = Field(..., description="UUID of user to request chat with")

class ChatRequestAction(BaseModel):
    action: Literal["accept", "decline"]

class ChatRequestResponse(BaseModel):
    id: UUID
    requester_id: UUID
    requester_name: str
    requester_avatar: Optional[str] = None
    recipient_id: UUID
    recipient_name: str
    recipient_avatar: Optional[str] = None
    status: str
    created_at: datetime
