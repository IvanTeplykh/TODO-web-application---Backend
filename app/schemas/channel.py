from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID

class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Channel title")
    description: Optional[str] = Field(None, max_length=250, description="Channel description")
    avatar_url: Optional[str] = Field(None, description="Channel avatar image URL")

class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=250)
    avatar_url: Optional[str] = Field(None)

class ChannelMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    avatar_url: Optional[str] = None
    role: str # owner, admin, member
    status: str = "accepted" # pending, accepted
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChannelResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    owner_id: UUID
    created_at: datetime
    my_role: Optional[str] = None
    members_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class AddMemberRequest(BaseModel):
    user_id: Optional[UUID] = None
    username: Optional[str] = None

class ChannelInviteResponse(BaseModel):
    id: UUID
    channel_id: UUID
    channel_name: str
    channel_description: Optional[str] = None
    channel_avatar: Optional[str] = None
    created_at: datetime

class UpdateMemberRoleRequest(BaseModel):
    role: Literal["admin", "member"]

class ChannelMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

class ChannelMessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

class ChannelMessageResponse(BaseModel):
    id: UUID
    channel_id: UUID
    sender_id: UUID
    sender_name: str
    sender_avatar: Optional[str] = None
    content: str
    content_hash: Optional[str] = None
    created_at: datetime
    is_edited: bool = False
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
