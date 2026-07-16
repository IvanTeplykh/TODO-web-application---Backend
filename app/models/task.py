from datetime import datetime
from pydantic import BaseModel, Field

class TaskDB(BaseModel):
    id: str = Field(alias="_id")
    title: str
    completed: bool
    priority: int
    created_at: datetime
    updated_at: datetime
    owner_id: str
