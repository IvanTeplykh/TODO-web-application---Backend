from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    priority: int = Field(..., ge=1, le=10)

class TaskUpdate(BaseModel):
    title: str = Field(..., min_length=1)
    priority: int = Field(..., ge=1, le=10)
    completed: bool

class TaskStatusUpdate(BaseModel):
    completed: bool

class TaskResponse(BaseModel):
    id: UUID
    title: str
    completed: bool
    priority: int
    created_at: datetime
    updated_at: datetime
    owner_id: UUID

    class Config:
        from_attributes = True
