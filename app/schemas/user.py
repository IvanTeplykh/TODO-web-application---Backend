from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    avatar_url: str | None = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    username: str
    avatar_url: str | None = None

class UserRegisterResponse(BaseModel):
    message: str
