from fastapi import APIRouter, Depends, Query, status
from uuid import UUID
from app.schemas.task import TaskCreate, TaskUpdate, TaskStatusUpdate, TaskResponse
from app.schemas.user import UserResponse
from app.services.task_service import TaskService
from app.dependencies.auth import get_current_user
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    return await TaskService.create_task(task_in, owner_id=current_user.id)

@router.get("", response_model=PaginatedResponse[TaskResponse])
async def get_tasks(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: str = Query("all", pattern="^(all|done|undone)$"),
    search: str | None = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: UserResponse = Depends(get_current_user)
):
    return await TaskService.get_tasks(
        owner_id=current_user.id,
        page=page,
        limit=limit,
        status_filter=status,
        search=search,
        sort=sort,
        order=order
    )

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: UserResponse = Depends(get_current_user)
):
    return await TaskService.get_task_by_id(task_id, owner_id=current_user.id)

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task_in: TaskUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    return await TaskService.update_task(task_id, task_in, owner_id=current_user.id)

@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: UUID,
    status_in: TaskStatusUpdate,
    current_user: UserResponse = Depends(get_current_user)
):
    return await TaskService.update_task_status(task_id, status_in, owner_id=current_user.id)

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    current_user: UserResponse = Depends(get_current_user)
):
    await TaskService.delete_task(task_id, owner_id=current_user.id)
