from fastapi import APIRouter, Depends, status
from app.schemas.user import UserResponse, UserUpdate
from app.dependencies.auth import get_current_user
from app.core.database import db
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
