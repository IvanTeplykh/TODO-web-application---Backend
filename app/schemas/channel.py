from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChannelCreate(BaseModel):
    # Expanded to VARCHAR(255) to support long/multilingual titles and emojis
    name: str = Field(..., min_length=1, max_length=255, description="Channel title")
    # Expanded to VARCHAR(500) for detailed channel onboarding and descriptions
    description: str | None = Field(None, max_length=500, description="Channel description")
    # Expanded to VARCHAR(500) to support long S3 presigned URLs & CDN paths
    avatar_url: str | None = Field(None, max_length=500, description="Channel avatar image URL")

class ChannelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    avatar_url: str | None = Field(None, max_length=500)

class ChannelMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    avatar_url: str | None = None
    role: str # owner, admin, member
    status: str = "accepted" # pending, accepted
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChannelResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    avatar_url: str | None = None
    owner_id: UUID
    created_at: datetime
    my_role: str | None = None
    members_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class AddMemberRequest(BaseModel):
    user_id: UUID | None = None
    username: str | None = None

class ChannelInviteResponse(BaseModel):
    id: UUID
    channel_id: UUID
    channel_name: str
    channel_description: str | None = None
    channel_avatar: str | None = None
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
    sender_avatar: str | None = None
    content: str
    content_hash: str | None = None
    created_at: datetime
    is_edited: bool = False
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
