from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: EmailStr
    avatar_url: str | None = None
    chat_retention_days: int = 180

    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    username: str
    avatar_url: str | None = None
    chat_retention_days: int = 180

class UserRegisterResponse(BaseModel):
    message: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class VerifyPasswordRequest(BaseModel):
    password: str

class DeleteAccountRequest(BaseModel):
    password: str


