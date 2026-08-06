import uuid
import math
import random
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc, and_, or_
from sqlalchemy.orm import selectinload

from app.models.task import TaskModel
from app.models.task_collaborator import TaskCollaboratorModel, TaskShareRequestModel, TaskHistoryModel, TaskCommentModel, TaskReadStatusModel
from app.models.user import UserModel
from app.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskStatusUpdate,
    TaskResponse,
    TaskCollaboratorResponse,
    TaskShareCreate,
    TaskShareResponse,
    TaskHistoryResponse,
    TaskCommentCreate,
    TaskCommentUpdate,
    TaskCommentResponse
)
from app.utils.pagination import PaginatedResponse
from app.utils.encryption import encrypt_text, decrypt_text, compute_hash
from app.core.connection_manager import connection_manager

class TaskService:
    @staticmethod
    async def record_history(
        session: AsyncSession,
        task_id: UUID,
        actor_id: UUID,
        action: str,
        details: Optional[str] = None
    ) -> None:
        history_entry = TaskHistoryModel(
            id=uuid.uuid4(),
            task_id=task_id,
            actor_id=actor_id,
            action=action,
            details=encrypt_text(details) if details else None,
            created_at=datetime.now(timezone.utc)
        )
        session.add(history_entry)

    @staticmethod
    async def _to_response(session: AsyncSession, task: TaskModel, current_user_id: UUID) -> TaskResponse:
        plain_title = decrypt_text(task.title) or ""
        plain_desc = decrypt_text(task.description)
        
        t_hash = task.title_hash or compute_hash(plain_title)
        d_hash = task.description_hash or compute_hash(plain_desc)
        p_hash = task.priority_hash or compute_hash(str(task.priority))
        c_hash = task.completed_hash or compute_hash(str(task.completed))

        # Determine owner username
        u_stmt = select(UserModel.username).where(UserModel.id == task.owner_id)
        u_res = await session.execute(u_stmt)
        owner_name = u_res.scalar_one_or_none() or "Unknown"

        # Determine my_access_level
        if task.owner_id == current_user_id:
            my_access_level = "owner"
        else:
            collab_stmt = select(TaskCollaboratorModel.access_level).where(
                and_(
                    TaskCollaboratorModel.task_id == task.id,
                    TaskCollaboratorModel.user_id == current_user_id
                )
            )
            collab_res = await session.execute(collab_stmt)
            my_access_level = collab_res.scalar_one_or_none() or "status_only"

        # Load collaborators
        collab_query = (
            select(TaskCollaboratorModel)
            .options(selectinload(TaskCollaboratorModel.user))
            .where(TaskCollaboratorModel.task_id == task.id)
            .order_by(TaskCollaboratorModel.created_at.asc())
        )
        collab_res = await session.execute(collab_query)
        collab_models = collab_res.scalars().all()

        collab_responses = []
        for c in collab_models:
            collab_responses.append(
                TaskCollaboratorResponse(
                    id=c.id,
                    user_id=c.user_id,
                    username=c.user.username if c.user else "Unknown",
                    avatar_url=decrypt_text(c.user.avatar_url) if (c.user and c.user.avatar_url) else None,
                    access_level=c.access_level,
                    created_at=c.created_at
                )
            )

        # Unread comments check
        read_stmt = select(TaskReadStatusModel.last_read_at).where(
            and_(TaskReadStatusModel.task_id == task.id, TaskReadStatusModel.user_id == current_user_id)
        )
        read_res = await session.execute(read_stmt)
        last_read_at = read_res.scalar_one_or_none()

        unread_conds = [
            TaskCommentModel.task_id == task.id,
            TaskCommentModel.user_id != current_user_id
        ]
        if last_read_at:
            unread_conds.append(TaskCommentModel.created_at > last_read_at)

        unread_stmt = select(func.count(TaskCommentModel.id)).where(and_(*unread_conds))
        unread_res = await session.execute(unread_stmt)
        unread_count = unread_res.scalar() or 0

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
            owner_id=task.owner_id,
            owner_username=owner_name,
            my_access_level=my_access_level,
            collaborators=collab_responses,
            has_unread_comments=(unread_count > 0),
            unread_comments_count=unread_count
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
            title=enc_title,
            title_hash=t_hash,
            completed=False,
            completed_hash=c_hash,
            priority=task_in.priority,
            priority_hash=p_hash,
            description=enc_desc,
            description_hash=d_hash,
            due_date=task_in.due_date,
            created_at=now,
            updated_at=now
        )
        
        session.add(new_task)
        await TaskService.record_history(session, task_id, owner_id, "created", f"Task created: '{task_in.title}'")
        await session.commit()
        await session.refresh(new_task)
        return await TaskService._to_response(session, new_task, owner_id)

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
        # Task IDs owned by user or shared with user
        subq = select(TaskCollaboratorModel.task_id).where(TaskCollaboratorModel.user_id == owner_id)
        conditions = [or_(TaskModel.owner_id == owner_id, TaskModel.id.in_(subq))]
        
        now = datetime.now(timezone.utc)
        if status_filter == "done":
            conditions.append(TaskModel.completed.is_(True))
        elif status_filter == "undone":
            conditions.append(TaskModel.completed.is_(False))
        elif status_filter == "overdue":
            conditions.append(TaskModel.completed.is_(False))
            conditions.append(and_(TaskModel.due_date.isnot(None), TaskModel.due_date < now))
        
        if search:
            search_hash = compute_hash(search.strip())
            conditions.append(or_(
                TaskModel.title_hash == search_hash,
                TaskModel.description_hash == search_hash
            ))
            
        count_stmt = select(func.count(TaskModel.id)).where(and_(*conditions))
        count_res = await session.execute(count_stmt)
        total = count_res.scalar() or 0
        
        allowed_sort_map = {
            "priority": TaskModel.priority,
            "created_at": TaskModel.created_at,
            "updated_at": TaskModel.updated_at,
            "title": TaskModel.title,
            "completed": TaskModel.completed,
            "due_date": TaskModel.due_date
        }
        sort_col = allowed_sort_map.get(sort, TaskModel.created_at)
        sort_expr = asc(sort_col) if order == "asc" else desc(sort_col)

        skip = (page - 1) * limit
        stmt = (
            select(TaskModel)
            .options(selectinload(TaskModel.owner))
            .where(and_(*conditions))
            .order_by(sort_expr)
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        task_docs = res.scalars().all()

        pages = math.ceil(total / limit) if total > 0 else 1
        items = [await TaskService._to_response(session, task, owner_id) for task in task_docs]
        
        return PaginatedResponse[TaskResponse](
            items=items,
            total=total,
            page=page,
            pages=pages
        )

    @staticmethod
    async def get_task_by_id(session: AsyncSession, task_id: UUID, owner_id: UUID) -> TaskResponse:
        stmt = select(TaskModel).options(selectinload(TaskModel.owner)).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        
        is_owner = (task.owner_id == owner_id)
        collab_stmt = select(TaskCollaboratorModel).where(
            and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id == owner_id)
        )
        collab_res = await session.execute(collab_stmt)
        is_collab = collab_res.scalar_one_or_none() is not None

        if not is_owner and not is_collab:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this task")
            
        return await TaskService._to_response(session, task, owner_id)

    @staticmethod
    async def update_task(session: AsyncSession, task_id: UUID, task_in: TaskUpdate, owner_id: UUID) -> TaskResponse:
        stmt = select(TaskModel).options(selectinload(TaskModel.owner)).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        
        is_owner = (task.owner_id == owner_id)
        collab_stmt = select(TaskCollaboratorModel.access_level).where(
            and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id == owner_id)
        )
        collab_res = await session.execute(collab_stmt)
        collab_level = collab_res.scalar_one_or_none()

        if not is_owner and collab_level != "full_access":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to modify task details")
            
        enc_title = encrypt_text(task_in.title)
        enc_desc = encrypt_text(task_in.description)
        t_hash = compute_hash(task_in.title)
        d_hash = compute_hash(task_in.description)
        p_hash = compute_hash(str(task_in.priority))
        c_hash = compute_hash(str(task_in.completed))

        task.title = enc_title
        task.title_hash = t_hash
        task.priority = task_in.priority
        task.priority_hash = p_hash
        task.completed = task_in.completed
        task.completed_hash = c_hash
        task.description = enc_desc
        task.description_hash = d_hash
        task.due_date = task_in.due_date
        task.updated_at = datetime.now(timezone.utc)
        
        await TaskService.record_history(session, task_id, owner_id, "updated", f"Task updated: '{task_in.title}'")
        await session.commit()
        await session.refresh(task)
        return await TaskService._to_response(session, task, owner_id)

    @staticmethod
    async def update_task_status(session: AsyncSession, task_id: UUID, status_in: TaskStatusUpdate, owner_id: UUID) -> TaskResponse:
        stmt = select(TaskModel).options(selectinload(TaskModel.owner)).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        
        is_owner = (task.owner_id == owner_id)
        collab_stmt = select(TaskCollaboratorModel).where(
            and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id == owner_id)
        )
        collab_res = await session.execute(collab_stmt)
        is_collab = collab_res.scalar_one_or_none() is not None

        if not is_owner and not is_collab:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to modify task status")
            
        c_hash = compute_hash(str(status_in.completed))
        task.completed = status_in.completed
        task.completed_hash = c_hash
        task.updated_at = datetime.now(timezone.utc)
        
        status_text = "completed" if status_in.completed else "pending"
        await TaskService.record_history(session, task_id, owner_id, "status_changed", f"Task status set to {status_text}")
        await session.commit()
        await session.refresh(task)
        return await TaskService._to_response(session, task, owner_id)

    @staticmethod
    async def delete_task(session: AsyncSession, task_id: UUID, owner_id: UUID) -> None:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        
        if task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only task owner can delete this task")
            
        await session.delete(task)
        await session.commit()

    @staticmethod
    async def create_share_request(
        session: AsyncSession,
        task_id: UUID,
        owner_id: UUID,
        data: TaskShareCreate
    ) -> TaskShareResponse:
        stmt = select(TaskModel).options(selectinload(TaskModel.owner)).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only task owner can invite/transfer users")

        u_stmt = select(UserModel).where(func.lower(UserModel.username) == data.target_username.strip().lower())
        u_res = await session.execute(u_stmt)
        target_user = u_res.scalar_one_or_none()

        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User @{data.target_username} not found")

        if target_user.id == owner_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot share task with yourself")

        # Check existing pending share request
        ex_req_stmt = select(TaskShareRequestModel).where(
            and_(
                TaskShareRequestModel.task_id == task_id,
                TaskShareRequestModel.target_user_id == target_user.id,
                TaskShareRequestModel.status == "pending"
            )
        )
        ex_req_res = await session.execute(ex_req_stmt)
        if ex_req_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pending invitation already sent to this user")

        # Generate 6-digit passcode
        passcode = f"{random.randint(100000, 999999)}"
        now = datetime.now(timezone.utc)

        share_req = TaskShareRequestModel(
            id=uuid.uuid4(),
            task_id=task_id,
            owner_id=owner_id,
            target_user_id=target_user.id,
            access_level=data.access_level,
            passcode=encrypt_text(passcode),
            status="pending",
            created_at=now
        )
        session.add(share_req)

        plain_title = decrypt_text(task.title) or "Task"
        await TaskService.record_history(
            session,
            task_id,
            owner_id,
            "share_requested",
            f"Share request ({data.access_level}) sent to @{target_user.username}"
        )

        await session.commit()
        await session.refresh(share_req)

        await connection_manager.send_personal_message(
            {
                "type": "task_share_requested",
                "request_id": str(share_req.id),
                "task_id": str(task.id),
                "task_title": plain_title,
                "owner_username": task.owner.username if task.owner else "Owner",
                "access_level": share_req.access_level
            },
            str(target_user.id)
        )

        return TaskShareResponse(
            id=share_req.id,
            task_id=task.id,
            task_title=plain_title,
            owner_id=owner_id,
            owner_username=task.owner.username if task.owner else "Owner",
            target_user_id=target_user.id,
            target_username=target_user.username,
            access_level=share_req.access_level,
            passcode=passcode, # Owner gets passcode to send to recipient
            status=share_req.status,
            created_at=share_req.created_at
        )

    @staticmethod
    async def get_pending_share_requests(session: AsyncSession, user_id: UUID) -> List[TaskShareResponse]:
        stmt = (
            select(TaskShareRequestModel)
            .options(
                selectinload(TaskShareRequestModel.task),
                selectinload(TaskShareRequestModel.owner),
                selectinload(TaskShareRequestModel.target_user)
            )
            .where(
                and_(
                    TaskShareRequestModel.target_user_id == user_id,
                    TaskShareRequestModel.status == "pending"
                )
            )
            .order_by(TaskShareRequestModel.created_at.desc())
        )
        res = await session.execute(stmt)
        requests = res.scalars().all()

        results = []
        for req in requests:
            plain_title = decrypt_text(req.task.title) if req.task else "Task"
            results.append(
                TaskShareResponse(
                    id=req.id,
                    task_id=req.task_id,
                    task_title=plain_title,
                    owner_id=req.owner_id,
                    owner_username=req.owner.username if req.owner else "Owner",
                    target_user_id=req.target_user_id,
                    target_username=req.target_user.username if req.target_user else "User",
                    access_level=req.access_level,
                    passcode=None, # Hidden for recipient until entered
                    status=req.status,
                    created_at=req.created_at
                )
            )
        return results

    @staticmethod
    async def respond_share_request(
        session: AsyncSession,
        request_id: UUID,
        user_id: UUID,
        passcode: str,
        action: str
    ) -> dict:
        stmt = (
            select(TaskShareRequestModel)
            .options(
                selectinload(TaskShareRequestModel.task),
                selectinload(TaskShareRequestModel.owner),
                selectinload(TaskShareRequestModel.target_user)
            )
            .where(
                and_(
                    TaskShareRequestModel.id == request_id,
                    TaskShareRequestModel.target_user_id == user_id,
                    TaskShareRequestModel.status == "pending"
                )
            )
        )
        res = await session.execute(stmt)
        req = res.scalar_one_or_none()

        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task share request not found")

        if action == "decline":
            req.status = "declined"
            await TaskService.record_history(
                session,
                req.task_id,
                user_id,
                "share_declined",
                f"Declined share request from @{req.owner.username if req.owner else 'Owner'}"
            )
            await session.commit()
            return {"message": "Task share request declined", "status": "declined"}

        if action == "accept":
            plain_passcode = decrypt_text(req.passcode) or req.passcode
            if plain_passcode.strip() != passcode.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid passcode provided")

            req.status = "accepted"

            if req.access_level == "transfer":
                old_owner_id = req.owner_id
                old_owner_name = req.owner.username if req.owner else "previous owner"
                new_owner_name = req.target_user.username if req.target_user else "new owner"
                req.task.owner_id = user_id
                
                # Clean up existing collaborator record for new owner if present
                del_collab = select(TaskCollaboratorModel).where(
                    and_(TaskCollaboratorModel.task_id == req.task_id, TaskCollaboratorModel.user_id == user_id)
                )
                del_res = await session.execute(del_collab)
                existing_c = del_res.scalar_one_or_none()
                if existing_c:
                    await session.delete(existing_c)

                # Add old owner as a status_only collaborator
                old_c_stmt = select(TaskCollaboratorModel).where(
                    and_(TaskCollaboratorModel.task_id == req.task_id, TaskCollaboratorModel.user_id == old_owner_id)
                )
                old_c_res = await session.execute(old_c_stmt)
                old_c = old_c_res.scalar_one_or_none()
                if old_c:
                    old_c.access_level = "status_only"
                else:
                    new_c = TaskCollaboratorModel(
                        id=uuid.uuid4(),
                        task_id=req.task_id,
                        user_id=old_owner_id,
                        access_level="status_only",
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(new_c)

                await TaskService.record_history(
                    session,
                    req.task_id,
                    user_id,
                    "ownership_transferred",
                    f"Ownership transferred from @{old_owner_name} to @{new_owner_name}. @{old_owner_name} is now a status-only collaborator."
                )
            else:
                # Add or update collaborator
                ex_c_stmt = select(TaskCollaboratorModel).where(
                    and_(TaskCollaboratorModel.task_id == req.task_id, TaskCollaboratorModel.user_id == user_id)
                )
                ex_c_res = await session.execute(ex_c_stmt)
                collab = ex_c_res.scalar_one_or_none()

                if collab:
                    collab.access_level = req.access_level
                else:
                    collab = TaskCollaboratorModel(
                        id=uuid.uuid4(),
                        task_id=req.task_id,
                        user_id=user_id,
                        access_level=req.access_level,
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(collab)

                await TaskService.record_history(
                    session,
                    req.task_id,
                    user_id,
                    "share_accepted",
                    f"Joined task as {req.access_level} collaborator"
                )

            await session.commit()

            plain_title = decrypt_text(req.task.title) if req.task else "Task"
            await connection_manager.send_personal_message(
                {
                    "type": "task_share_responded",
                    "request_id": str(request_id),
                    "task_id": str(req.task_id),
                    "task_title": plain_title,
                    "action": action,
                    "target_username": req.target_user.username if req.target_user else "User"
                },
                str(req.owner_id)
            )
            await connection_manager.send_personal_message(
                {
                    "type": "task_share_responded",
                    "request_id": str(request_id),
                    "task_id": str(req.task_id),
                    "task_title": plain_title,
                    "action": action
                },
                str(user_id)
            )

            return {"message": "Task share request accepted", "status": "accepted", "task_id": str(req.task_id)}

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")

    @staticmethod
    async def get_task_history(session: AsyncSession, task_id: UUID, user_id: UUID) -> List[TaskHistoryResponse]:
        # Permission check
        await TaskService.get_task_by_id(session, task_id, user_id)

        stmt = (
            select(TaskHistoryModel)
            .options(selectinload(TaskHistoryModel.actor))
            .where(TaskHistoryModel.task_id == task_id)
            .order_by(TaskHistoryModel.created_at.desc())
        )
        res = await session.execute(stmt)
        history_entries = res.scalars().all()

        results = []
        for h in history_entries:
            results.append(
                TaskHistoryResponse(
                    id=h.id,
                    task_id=h.task_id,
                    actor_id=h.actor_id,
                    actor_name=h.actor.username if h.actor else "System",
                    action=h.action,
                    details=decrypt_text(h.details),
                    created_at=h.created_at
                )
            )
        return results

    @staticmethod
    async def remove_collaborator(session: AsyncSession, task_id: UUID, owner_id: UUID, target_user_id: UUID) -> dict:
        stmt = select(TaskModel).where(TaskModel.id == task_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task or task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only task owner can remove collaborators")

        collab_stmt = select(TaskCollaboratorModel).where(
            and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id == target_user_id)
        )
        collab_res = await session.execute(collab_stmt)
        collab = collab_res.scalar_one_or_none()

        if not collab:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaborator not found")

        u_stmt = select(UserModel.username).where(UserModel.id == target_user_id)
        u_res = await session.execute(u_stmt)
        target_name = u_res.scalar_one_or_none() or "user"

        await session.delete(collab)
        await TaskService.record_history(session, task_id, owner_id, "collaborator_removed", f"Removed collaborator @{target_name}")
        await session.commit()

        await connection_manager.send_personal_message(
            {
                "type": "task_collaborator_removed",
                "task_id": str(task_id)
            },
            str(target_user_id)
        )

        return {"message": f"Collaborator @{target_name} removed"}

    @staticmethod
    async def get_task_comments(session: AsyncSession, task_id: UUID, user_id: UUID) -> List[TaskCommentResponse]:
        await TaskService.get_task_by_id(session, task_id, user_id)

        # Mark comments as read for user
        read_stmt = select(TaskReadStatusModel).where(
            and_(TaskReadStatusModel.task_id == task_id, TaskReadStatusModel.user_id == user_id)
        )
        read_res = await session.execute(read_stmt)
        read_status = read_res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if read_status:
            read_status.last_read_at = now
        else:
            read_status = TaskReadStatusModel(
                id=uuid.uuid4(),
                task_id=task_id,
                user_id=user_id,
                last_read_at=now
            )
            session.add(read_status)
        await session.commit()

        stmt = (
            select(TaskCommentModel)
            .options(selectinload(TaskCommentModel.author))
            .where(TaskCommentModel.task_id == task_id)
            .order_by(TaskCommentModel.created_at.asc())
        )
        res = await session.execute(stmt)
        comments = res.scalars().all()

        results = []
        for c in comments:
            results.append(
                TaskCommentResponse(
                    id=c.id,
                    task_id=c.task_id,
                    user_id=c.user_id,
                    author_name=c.author.username if c.author else "Unknown",
                    author_avatar_url=decrypt_text(c.author.avatar_url) if (c.author and c.author.avatar_url) else None,
                    content=decrypt_text(c.content) or c.content,
                    created_at=c.created_at,
                    updated_at=c.updated_at
                )
            )
        return results

    @staticmethod
    async def create_task_comment(
        session: AsyncSession,
        task_id: UUID,
        user_id: UUID,
        data: TaskCommentCreate
    ) -> TaskCommentResponse:
        await TaskService.get_task_by_id(session, task_id, user_id)

        u_stmt = select(UserModel).where(UserModel.id == user_id)
        u_res = await session.execute(u_stmt)
        user = u_res.scalar_one_or_none()

        comment_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        comment = TaskCommentModel(
            id=comment_id,
            task_id=task_id,
            user_id=user_id,
            content=encrypt_text(data.content.strip()),
            created_at=now,
            updated_at=now
        )
        session.add(comment)

        preview = data.content.strip()[:30] + ("..." if len(data.content.strip()) > 30 else "")
        await TaskService.record_history(session, task_id, user_id, "comment_added", f"Comment added: '{preview}'")

        await session.commit()
        await session.refresh(comment)

        # Broadcast real-time comment notification to owner & collaborators
        task_stmt = (
            select(TaskModel)
            .options(selectinload(TaskModel.collaborators))
            .where(TaskModel.id == task_id)
        )
        task_res = await session.execute(task_stmt)
        task_db = task_res.scalar_one_or_none()

        if task_db:
            target_ids = set()
            if task_db.owner_id != user_id:
                target_ids.add(str(task_db.owner_id))
            for c in task_db.collaborators:
                if c.user_id != user_id:
                    target_ids.add(str(c.user_id))

            for tid in target_ids:
                await connection_manager.send_personal_message(
                    {
                        "type": "task_comment_added",
                        "task_id": str(task_id),
                        "author_name": user.username if user else "User"
                    },
                    tid
                )

        return TaskCommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            user_id=comment.user_id,
            author_name=user.username if user else "Unknown",
            author_avatar_url=decrypt_text(user.avatar_url) if (user and user.avatar_url) else None,
            content=data.content.strip(),
            created_at=comment.created_at,
            updated_at=comment.updated_at
        )

    @staticmethod
    async def update_task_comment(
        session: AsyncSession,
        task_id: UUID,
        comment_id: UUID,
        user_id: UUID,
        data: TaskCommentUpdate
    ) -> TaskCommentResponse:
        stmt = (
            select(TaskCommentModel)
            .options(selectinload(TaskCommentModel.author))
            .where(and_(TaskCommentModel.id == comment_id, TaskCommentModel.task_id == task_id))
        )
        res = await session.execute(stmt)
        comment = res.scalar_one_or_none()

        if not comment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

        if comment.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own comments")

        comment.content = encrypt_text(data.content.strip())
        comment.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(comment)

        return TaskCommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            user_id=comment.user_id,
            author_name=comment.author.username if comment.author else "Unknown",
            author_avatar_url=decrypt_text(comment.author.avatar_url) if (comment.author and comment.author.avatar_url) else None,
            content=data.content.strip(),
            created_at=comment.created_at,
            updated_at=comment.updated_at
        )

    @staticmethod
    async def delete_task_comment(
        session: AsyncSession,
        task_id: UUID,
        comment_id: UUID,
        user_id: UUID
    ) -> None:
        task_stmt = select(TaskModel).where(TaskModel.id == task_id)
        task_res = await session.execute(task_stmt)
        task = task_res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        stmt = select(TaskCommentModel).where(and_(TaskCommentModel.id == comment_id, TaskCommentModel.task_id == task_id))
        res = await session.execute(stmt)
        comment = res.scalar_one_or_none()

        if not comment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

        if comment.user_id != user_id and task.owner_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this comment")

        await session.delete(comment)
        await session.commit()

    @staticmethod
    async def reassign_tasks_before_user_deletion(session: AsyncSession, user_id: UUID) -> None:
        task_stmt = select(TaskModel).where(TaskModel.owner_id == user_id)
        task_res = await session.execute(task_stmt)
        owned_tasks = task_res.scalars().all()

        u_stmt = select(UserModel.username).where(UserModel.id == user_id)
        u_res = await session.execute(u_stmt)
        old_owner_name = u_res.scalar_one_or_none() or "previous owner"

        for task in owned_tasks:
            collab_stmt = (
                select(TaskCollaboratorModel)
                .options(selectinload(TaskCollaboratorModel.user))
                .where(
                    and_(
                        TaskCollaboratorModel.task_id == task.id,
                        TaskCollaboratorModel.user_id != user_id
                    )
                )
                .order_by(TaskCollaboratorModel.created_at.asc())
            )
            collab_res = await session.execute(collab_stmt)
            collaborators = collab_res.scalars().all()

            if not collaborators:
                continue

            # 1. Search for first Co-Owner (access_level == 'full_access')
            new_owner_collab = next((c for c in collaborators if c.access_level == "full_access"), None)

            # 2. Fallback to first Collaborator (access_level == 'status_only')
            if not new_owner_collab:
                new_owner_collab = collaborators[0]

            new_owner_id = new_owner_collab.user_id
            new_owner_name = new_owner_collab.user.username if new_owner_collab.user else "new owner"

            # Re-assign ownership
            task.owner_id = new_owner_id

            # Remove new owner from collaborators list
            await session.delete(new_owner_collab)

            # Record history entry
            await TaskService.record_history(
                session,
                task.id,
                new_owner_id,
                "ownership_transferred",
                f"Ownership automatically transferred to @{new_owner_name} due to account deletion of former owner @{old_owner_name}."
            )

            # Notify new owner via WebSocket
            plain_title = decrypt_text(task.title) or "Task"
            await connection_manager.send_personal_message(
                {
                    "type": "task_ownership_transferred",
                    "task_id": str(task.id),
                    "task_title": plain_title,
                    "new_owner_username": new_owner_name
                },
                str(new_owner_id)
            )

        await session.commit()
                                                                              