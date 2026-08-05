import uuid
import math
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc, and_, or_
from app.models.task import TaskModel
from app.schemas.task import TaskCreate, TaskUpdate, TaskStatusUpdate, TaskResponse
from app.utils.pagination import PaginatedResponse
from app.utils.encryption import encrypt_text, decrypt_text, compute_hash

class TaskService:
    @staticmethod
    def _to_response(task: TaskModel) -> TaskResponse:
        plain_title = decrypt_text(task.encrypted_title) or ""
        plain_desc = decrypt_text(task.encrypted_description)
        
        t_hash = task.title_hash or compute_hash(plain_title)
        d_hash = task.description_hash or compute_hash(plain_desc)
        p_hash = task.priority_hash or compute_hash(str(task.priority))
        c_hash = task.completed_hash or compute_hash(str(task.completed))

        return TaskResponse(
            id=task.id,
            title=plain_title,
            title_hash=t_hash,
            completed=task.completed,
            completed_hash=c_hash,
            priority=task.priority,
            priority_hash=p_hash,
            description=plain_desc,
            description_hash=d_hash,
            due_date=task.due_date,
            created_at=task.created_at,
            updated_at=task.updated_at,
            owner_id=task.owner_id
        )

    @staticmethod
    async def create_task(session: AsyncSession, task_in: TaskCreate, owner_id: UUID) -> TaskResponse:
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        
        enc_title = encrypt_text(task_in.title)
        enc_desc = encrypt_text(task_in.description)
        t_hash = compute_hash(task_in.title)
        d_hash = compute_hash(task_in.description)
        p_hash = compute_hash(str(task_in.priority))
        c_hash = compute_hash("False")

        new_task = TaskModel(
            id=task_id,
            owner_id=owner_id,
            encrypted_title=enc_title,
            title_hash=t_hash,
            completed=False,
            completed_hash=c_hash,
            priority=task_in.priority,
            priority_hash=p_hash,
            encrypted_description=enc_desc,
            description_hash=d_hash,
            due_date=task_in.due_date,
            created_at=now,
            updated_at=now
        )
        
        session.add(new_task)
        await session.commit()
        await session.refresh(new_task)
        return TaskService._to_response(new_task)

    @staticmethod
    async def get_tasks(
        session: AsyncSession,
        owner_id: UUID,
        page: int,
        limit: int,
        status_filter: str,
        search: str | None,
        sort: str,
        order: str
    ) -> PaginatedResponse[TaskResponse]:
        conditions = [TaskModel.owner_id == owner_id]
        
        now = datetime.now(timezone.utc)
        if status_filter == "done":
            conditions.append(TaskModel.completed.is_(True))
        elif status_filter == "undone":
            conditions.append(TaskModel.completed.is_(False))
        elif status_filter == "overdue":
            conditions.append(TaskModel.completed.is_(False))
            conditions.append(and_(TaskModel.due_date.isnot(None), TaskModel.due_date < now))
        
        if search:
            search_hash = compute_hash(search)
            conditions.append(or_(
                TaskModel.title_hash == search_hash,
                TaskModel.description_hash == search_hash,
                TaskModel.title_hash.ilike(f"%{search}%"),
                TaskModel.description_hash.ilike(f"%{search}%")
            ))
            
        count_stmt = select(func.count(TaskModel.id)).where(and_(*conditions))
        count_res = await session.execute(count_stmt)
        total = count_res.scalar() or 0
        
        allowed_sort_map = {
            "priority": TaskModel.priority,
            "created_at": TaskModel.created_at,
            "updated_at": TaskModel.updated_at,
            "title": TaskModel.title_hash,
            "completed": TaskModel.completed,
            "due_date": TaskModel.due_date
        }
        sort_col = allowed_sort_map.get(sort, TaskModel.created_at)
        sort_expr = asc(sort_col) if order == "asc" else desc(sort_col)

        skip = (page - 1) * limit
        stmt = select(TaskModel).where(and_(*conditions)).order_by(sort_expr).offset(skip).limit(limit)
        res = await session.execute(stmt)
        task_docs = res.scalars().all()

        pages = math.ceil(total / limit) if total > 0 else 1
        items = [TaskService._to_response(task) for task in task_docs]
        
        return PaginatedResponse[TaskResponse](
            items=items,
            total=total,
            page=page,
            pages=pages
        )

    @staticmethod
    async def get_task_by_id(session: AsyncSession, task_id: UUID, owner_id: UUID) -> TaskResponse:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this task"
            )
            
        return TaskService._to_response(task)

    @staticmethod
    async def update_task(session: AsyncSession, task_id: UUID, task_in: TaskUpdate, owner_id: UUID) -> TaskResponse:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this task"
            )
            
        enc_title = encrypt_text(task_in.title)
        enc_desc = encrypt_text(task_in.description)
        t_hash = compute_hash(task_in.title)
        d_hash = compute_hash(task_in.description)
        p_hash = compute_hash(str(task_in.priority))
        c_hash = compute_hash(str(task_in.completed))

        task.encrypted_title = enc_title
        task.title_hash = t_hash
        task.priority = task_in.priority
        task.priority_hash = p_hash
        task.completed = task_in.completed
        task.completed_hash = c_hash
        task.encrypted_description = enc_desc
        task.description_hash = d_hash
        task.due_date = task_in.due_date
        task.updated_at = datetime.now(timezone.utc)
        
        await session.commit()
        await session.refresh(task)
        return TaskService._to_response(task)

    @staticmethod
    async def update_task_status(session: AsyncSession, task_id: UUID, status_in: TaskStatusUpdate, owner_id: UUID) -> TaskResponse:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this task"
            )
            
        c_hash = compute_hash(str(status_in.completed))
        task.completed = status_in.completed
        task.completed_hash = c_hash
        task.updated_at = datetime.now(timezone.utc)
        
        await session.commit()
        await session.refresh(task)
        return TaskService._to_response(task)

    @staticmethod
    async def delete_task(session: AsyncSession, task_id: UUID, owner_id: UUID) -> None:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this task"
            )
            
        await session.delete(task)
        await session.commit()
