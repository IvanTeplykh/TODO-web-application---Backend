from fastapi import APIRouter, Depends, status
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserResponse, UserRegisterResponse
from app.services.auth_service import AuthService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/check-email")
async def check_email(email: str):
    exists = await AuthService.check_email_exists(email)
    return {"exists": exists}

@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate):
    return await AuthService.register_user(user_in)

@router.post("/login", response_model=Token)
async def login(login_in: LoginRequest):
    return await AuthService.authenticate_user(login_in)

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(current_user: UserResponse = Depends(get_current_user)):
    return {"message": "Logged out successfully"}
