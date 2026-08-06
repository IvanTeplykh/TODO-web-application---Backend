from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRegisterResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/check-email")
async def check_email(email: str, session: AsyncSession = Depends(get_db)):
    exists = await AuthService.check_email_exists(session, email)
    return {"exists": exists}

@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, session: AsyncSession = Depends(get_db)):
    return await AuthService.register_user(session, user_in)

@router.post("/login", response_model=Token)
async def login(login_in: LoginRequest, session: AsyncSession = Depends(get_db)):
    return await AuthService.authenticate_user(session, login_in)

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(current_user: UserResponse = Depends(get_current_user)):
    return {"message": "Logged out successfully"}
