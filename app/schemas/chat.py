from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ChatUser(BaseModel):
    id: UUID
    username: str
    email: str
    avatar_url: Optional[str] = None
    is_online: bool = False

class MessageCreate(BaseModel):
    recipient_id: str = Field(..., description="UUID of recipient user or 'global'")
    content: str = Field(..., min_length=1, max_length=2000, description="Message text content")

class MessageResponse(BaseModel):
    id: UUID
    sender_id: UUID
    sender_name: str
    sender_avatar: Optional[str] = None
    recipient_id: str
    content: str
    created_at: datetime
