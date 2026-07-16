from datetime import datetime
from pydantic import BaseModel, Field

class UserDB(BaseModel):
    id: str = Field(alias="_id")
    username: str
    email: str
    password: str
    created_at: datetime
