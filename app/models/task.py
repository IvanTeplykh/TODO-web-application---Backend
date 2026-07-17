from datetime import datetime
from pydantic import BaseModel, Field

class TaskDB(BaseModel):
    id: str = Field(alias="_id")
    title: str
    completed: bool
    priority: int
    description: str | None = None
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    owner_id: str
