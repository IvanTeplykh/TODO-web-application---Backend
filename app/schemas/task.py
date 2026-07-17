from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

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

class TaskResponse(BaseModel):
    id: UUID
    title: str
    completed: bool
    priority: int
    description: str | None = None
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    owner_id: UUID

    class Config:
        from_attributes = True
