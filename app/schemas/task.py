from datetime import datetime
from uuid import UUID
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    priority: int = Field(..., ge=1, le=10)
    description: str | None = Field(None, max_length=500)
    due_date: datetime | None = None

class TaskUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    priority: int = Field(..., ge=1, le=10)
    completed: bool
    description: str | None = Field(None, max_length=500)
    due_date: datetime | None = None

class TaskStatusUpdate(BaseModel):
    completed: bool

class TaskCollaboratorResponse(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    avatar_url: Optional[str] = None
    access_level: str # status_only, full_access
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TaskShareCreate(BaseModel):
    target_username: str = Field(..., min_length=1, description="Username to share/transfer task to")
    access_level: Literal["transfer", "status_only", "full_access"]

class TaskShareResponse(BaseModel):
    id: UUID
    task_id: UUID
    task_title: str
    owner_id: UUID
    owner_username: str
    target_user_id: UUID
    target_username: str
    access_level: str # transfer, status_only, full_access
    passcode: Optional[str] = None # Returned to owner when created
    status: str # pending, accepted, declined
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TaskShareRespond(BaseModel):
    passcode: str = Field(..., min_length=1, description="Passcode provided by owner")
    action: Literal["accept", "decline"]

class TaskHistoryResponse(BaseModel):
    id: UUID
    task_id: UUID
    actor_id: UUID
    actor_name: str
    action: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TaskCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class TaskCommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class TaskCommentResponse(BaseModel):
    id: UUID
    task_id: UUID
    user_id: UUID
    author_name: str
    author_avatar_url: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TaskResponse(BaseModel):
    id: UUID
    title: str
    title_hash: Optional[str] = Field(None, description="SHA-256 integrity hash of task title")
    completed: bool
    completed_hash: Optional[str] = Field(None, description="SHA-256 integrity hash of task completed status")
    priority: int
    priority_hash: Optional[str] = Field(None, description="SHA-256 integrity hash of task priority")
    description: str | None = None
    description_hash: Optional[str] = Field(None, description="SHA-256 integrity hash of task description")
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    owner_id: UUID
    owner_username: Optional[str] = None
    my_access_level: str = "owner" # owner, full_access, status_only
    collaborators: List[TaskCollaboratorResponse] = []
    has_unread_comments: bool = False
    unread_comments_count: int = 0

    model_config = ConfigDict(from_attributes=True)
