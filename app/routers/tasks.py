from fastapi import APIRouter, Depends, Query, status
from uuid import UUID
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskStatusUpdate,
    TaskResponse,
    TaskShareCreate,
    TaskShareResponse,
    TaskShareRespond,
    TaskHistoryResponse,
    TaskCommentCreate,
    TaskCommentUpdate,
    TaskCommentResponse
)
from app.schemas.user import UserResponse
from app.services.task_service import TaskService
from app.dependencies.auth import get_current_user
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.create_task(session, task_in, owner_id=current_user.id)

@router.get("", response_model=PaginatedResponse[TaskResponse])
async def get_tasks(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=500),
    status: str = Query("all", pattern="^(all|done|undone|overdue)$"),
    search: str | None = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.get_tasks(
        session=session,
        owner_id=current_user.id,
        page=page,
        limit=limit,
        status_filter=status,
        search=search,
        sort=sort,
        order=order
    )

@router.get("/shares/pending", response_model=List[TaskShareResponse])
async def get_pending_task_shares(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.get_pending_share_requests(session, current_user.id)

@router.post("/shares/{request_id}/respond")
async def respond_task_share(
    request_id: UUID,
    payload: TaskShareRespond,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.respond_share_request(
        session,
        request_id,
        current_user.id,
        payload.passcode,
        payload.action
    )

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.get_task_by_id(session, task_id, owner_id=current_user.id)

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task_in: TaskUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.update_task(session, task_id, task_in, owner_id=current_user.id)

@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status_in: TaskStatusUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.update_task_status(session, task_id, status_in, owner_id=current_user.id)

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    await TaskService.delete_task(session, task_id, owner_id=current_user.id)

@router.post("/{task_id}/share", response_model=TaskShareResponse, status_code=status.HTTP_201_CREATED)
async def share_task(
    task_id: UUID,
    payload: TaskShareCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.create_share_request(session, task_id, current_user.id, payload)

@router.get("/{task_id}/history", response_model=List[TaskHistoryResponse])
async def get_task_history(
    task_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.get_task_history(session, task_id, current_user.id)

@router.delete("/{task_id}/collaborators/{target_user_id}")
async def remove_collaborator(
    task_id: UUID,
    target_user_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.remove_collaborator(session, task_id, current_user.id, target_user_id)

@router.get("/{task_id}/comments", response_model=List[TaskCommentResponse])
async def get_task_comments(
    task_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.get_task_comments(session, task_id, current_user.id)

@router.post("/{task_id}/comments", response_model=TaskCommentResponse, status_code=status.HTTP_201_CREATED)
async def create_task_comment(
    task_id: UUID,
    payload: TaskCommentCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.create_task_comment(session, task_id, current_user.id, payload)

@router.put("/{task_id}/comments/{comment_id}", response_model=TaskCommentResponse)
async def update_task_comment(
    task_id: UUID,
    comment_id: UUID,
    payload: TaskCommentUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    return await TaskService.update_task_comment(session, task_id, comment_id, current_user.id, payload)

@router.delete("/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_comment(
    task_id: UUID,
    comment_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    await TaskService.delete_task_comment(session, task_id, comment_id, current_user.id)
