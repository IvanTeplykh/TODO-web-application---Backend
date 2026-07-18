from fastapi import APIRouter, Depends, status, HTTPException
from app.schemas.user import UserResponse, UserUpdate, ChangePasswordRequest
from app.dependencies.auth import get_current_user
from app.core.database import db
from app.core.security import verify_password, get_password_hash
from uuid import UUID

router = APIRouter(prefix="/users", tags=["users"])

@router.put("/me", response_model=UserResponse)
async def update_profile(
    profile_in: UserUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    update_data = {
        "username": profile_in.username,
        "avatar_url": profile_in.avatar_url
    }
    
    await db.users_collection.update_one(
        {"_id": str(current_user.id)},
        {"$set": update_data}
    )
    
    # Fetch updated user
    updated_user = await db.users_collection.find_one({"_id": str(current_user.id)})
    
    return UserResponse(
        id=UUID(updated_user["_id"]),
        username=updated_user["username"],
        email=updated_user["email"],
        avatar_url=updated_user.get("avatar_url")
    )

@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: UserResponse = Depends(get_current_user)
):
    user = await db.users_collection.find_one({"_id": str(current_user.id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    if not verify_password(data.current_password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
        
    hashed_password = get_password_hash(data.new_password)
    
    await db.users_collection.update_one(
        {"_id": str(current_user.id)},
        {"$set": {"password": hashed_password}}
    )
    
    return {"message": "Password changed successfully"}
