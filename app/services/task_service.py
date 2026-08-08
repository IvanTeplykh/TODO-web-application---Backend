import math
import random
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.connection_manager import connection_manager
from app.core.crypto import compute_hmac_index, decrypt_field, encrypt_field
from app.core.security import get_passcode_hash, verify_passcode
from app.models.task import TaskModel
from app.models.task_collaborator import (
    TaskCollaboratorModel,
    TaskCommentModel,
    TaskHistoryModel,
    TaskReadStatusModel,
    TaskShareRequestModel,
)
from app.models.user import UserModel
from app.schemas.task import (
    TaskCollaboratorResponse,
    TaskCommentCreate,
    TaskCommentResponse,
    TaskCommentUpdate,
    TaskCreate,
    TaskHistoryResponse,
    TaskResponse,
    TaskShareCreate,
    TaskShareResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.utils.pagination import PaginatedResponse


def _str(val) -> str:
    if val is None:
        return ""
    return val.value if hasattr(val, "value") else str(val)


class TaskService:
    @staticmethod
    async def record_history(
        session: AsyncSession,
        task_id: UUID,
        actor_id: UUID,
        action: str,
        details: str | None = None
    ) -> None:
        history_entry = TaskHistoryModel(
            id=uuid.uuid4(),
            task_id=task_id,
            actor_id=actor_id,
            action=action,
            details=encrypt_field(details) if details else None,
            created_at=datetime.now(timezone.utc)
        )
        session.add(history_entry)

    @staticmethod
    async def _to_response(
        session: AsyncSession,
        task: TaskModel,
        current_user_id: UUID,
        read_status_map: dict[UUID, datetime] | None = None,
        unread_map: dict[UUID, int] | None = None,
        my_access_levels: dict[UUID, str] | None = None,
        avatar_cache: dict[str, str | None] | None = None,
    ) -> TaskResponse:
        plain_title = decrypt_field(task.title_encrypted) or ""
        plain_desc = decrypt_field(task.description_encrypted)

        t_hash = task.title_index or compute_hmac_index(plain_title)
        d_hash = task.description_index or (compute_hmac_index(plain_desc) if plain_desc else None)
        p_hash = compute_hmac_index(str(task.priority))
        c_hash = compute_hmac_index(str(task.completed))

        from sqlalchemy.orm.attributes import instance_state
        task_state = instance_state(task)

        # 1. Owner name (use pre-loaded task.owner if available, fallback to single query only if not loaded)
        if "owner" in task_state.dict and task.owner:
            owner_name = task.owner.username
        else:
            u_stmt = select(UserModel.username).where(UserModel.id == task.owner_id)
            u_res = await session.execute(u_stmt)
            owner_name = u_res.scalar_one_or_none() or "Unknown"

        # 2. My access level (use precomputed map if provided, else compute)
        if task.owner_id == current_user_id:
            my_access_level = "owner"
        elif my_access_levels is not None:
            my_access_level = my_access_levels.get(task.id, "status_only")
        else:
            collab_stmt = select(TaskCollaboratorModel.access_level).where(
                and_(
                    TaskCollaboratorModel.task_id == task.id,
                    TaskCollaboratorModel.user_id == current_user_id
                )
            )
            collab_res = await session.execute(collab_stmt)
            raw_access = collab_res.scalar_one_or_none()
            my_access_level = _str(raw_access) if raw_access else "status_only"

        # 3. Collaborators (use pre-loaded task.collaborators if loaded, fallback to query)
        if "collaborators" in task_state.dict and task.collaborators is not None:
            collab_models = sorted(task.collaborators, key=lambda c: c.created_at)
        else:
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
            c_state = instance_state(c)
            user_obj = c.user if ("user" in c_state.dict and c.user) else None
            dec_avatar = None
            if user_obj and user_obj.avatar_url:
                if avatar_cache is not None:
                    if user_obj.avatar_url not in avatar_cache:
                        avatar_cache[user_obj.avatar_url] = decrypt_field(user_obj.avatar_url)
                    dec_avatar = avatar_cache[user_obj.avatar_url]
                else:
                    dec_avatar = decrypt_field(user_obj.avatar_url)

            collab_responses.append(
                TaskCollaboratorResponse(
                    id=c.id,
                    user_id=c.user_id,
                    username=user_obj.username if user_obj else "Unknown",
                    avatar_url=dec_avatar,
                    access_level=_str(c.access_level),
                    created_at=c.created_at
                )
            )

        # 4. Unread comments count (use precomputed unread_map if provided, else execute single query)
        if unread_map is not None:
            unread_count = unread_map.get(task.id, 0)
        else:
            if read_status_map is not None:
                last_read_at = read_status_map.get(task.id)
            else:
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

        enc_title = encrypt_field(task_in.title)
        t_index = compute_hmac_index(task_in.title)

        enc_desc = encrypt_field(task_in.description) if task_in.description else None
        d_index = compute_hmac_index(task_in.description) if task_in.description else None

        new_task = TaskModel(
            id=task_id,
            owner_id=owner_id,
            title_encrypted=enc_title,
            title_index=t_index,
            completed=False,
            priority=task_in.priority,
            description_encrypted=enc_desc,
            description_index=d_index,
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
        # Pre-fetch collaborated task IDs to enable instant B-Tree index scans in PostgreSQL
        if status_filter == "collaborator":
            collab_ids_stmt = select(TaskCollaboratorModel.task_id).where(
                and_(
                    TaskCollaboratorModel.user_id == owner_id,
                    TaskCollaboratorModel.access_level == "status_only"
                )
            )
            collab_res = await session.execute(collab_ids_stmt)
            collab_ids = collab_res.scalars().all()
            conditions = [
                TaskModel.deleted_at == None,
                TaskModel.id.in_(collab_ids)
            ]
        elif status_filter == "co_owner":
            co_ids_stmt = select(TaskCollaboratorModel.task_id).where(
                and_(
                    TaskCollaboratorModel.user_id == owner_id,
                    TaskCollaboratorModel.access_level == "full_access"
                )
            )
            co_res = await session.execute(co_ids_stmt)
            co_ids = co_res.scalars().all()
            conditions = [
                TaskModel.deleted_at == None,
                TaskModel.id.in_(co_ids)
            ]
        else:
            all_collab_stmt = select(TaskCollaboratorModel.task_id).where(TaskCollaboratorModel.user_id == owner_id)
            all_collab_res = await session.execute(all_collab_stmt)
            collab_task_ids = all_collab_res.scalars().all()

            if collab_task_ids:
                conditions = [
                    TaskModel.deleted_at == None,
                    or_(TaskModel.owner_id == owner_id, TaskModel.id.in_(collab_task_ids))
                ]
            else:
                conditions = [
                    TaskModel.deleted_at == None,
                    TaskModel.owner_id == owner_id
                ]

        now = datetime.now(timezone.utc)
        if status_filter == "done":
            conditions.append(TaskModel.completed.is_(True))
        elif status_filter == "undone":
            conditions.append(TaskModel.completed.is_(False))
        elif status_filter == "overdue":
            conditions.append(TaskModel.completed.is_(False))
            conditions.append(and_(TaskModel.due_date.isnot(None), TaskModel.due_date < now))

        if search and search.strip():
            search_index = compute_hmac_index(search)
            conditions.append(or_(
                TaskModel.title_index == search_index,
                TaskModel.description_index == search_index
            ))

        count_stmt = select(func.count(TaskModel.id)).where(and_(*conditions))
        count_res = await session.execute(count_stmt)
        total = count_res.scalar() or 0

        allowed_sort_map = {
            "priority": TaskModel.priority,
            "created_at": TaskModel.created_at,
            "updated_at": TaskModel.updated_at,
            "completed": TaskModel.completed,
            "due_date": TaskModel.due_date
        }
        sort_col = allowed_sort_map.get(sort, TaskModel.created_at)
        sort_expr = asc(sort_col) if order == "asc" else desc(sort_col)

        from sqlalchemy.orm import joinedload, selectinload
        skip = (page - 1) * limit
        stmt = (
            select(TaskModel)
            .options(
                joinedload(TaskModel.owner),
                selectinload(TaskModel.collaborators).joinedload(TaskCollaboratorModel.user)
            )
            .where(and_(*conditions))
            .order_by(sort_expr)
            .offset(skip)
            .limit(limit)
        )
        res = await session.execute(stmt)
        tasks = res.scalars().unique().all()

        task_ids = [t.id for t in tasks]
        unread_map: dict[UUID, int] = {}
        my_access_levels: dict[UUID, str] = {}

        for t in tasks:
            if t.owner_id == owner_id:
                my_access_levels[t.id] = "owner"
            else:
                collab = next((c for c in t.collaborators if c.user_id == owner_id), None)
                my_access_levels[t.id] = _str(collab.access_level) if collab else "status_only"

        if task_ids:
            # Single consolidated GROUP BY query for unread comments count
            unread_stmt = (
                select(TaskCommentModel.task_id, func.count(TaskCommentModel.id))
                .outerjoin(
                    TaskReadStatusModel,
                    and_(
                        TaskReadStatusModel.task_id == TaskCommentModel.task_id,
                        TaskReadStatusModel.user_id == owner_id
                    )
                )
                .where(
                    and_(
                        TaskCommentModel.task_id.in_(task_ids),
                        TaskCommentModel.user_id != owner_id,
                        or_(
                            TaskReadStatusModel.last_read_at.is_(None),
                            TaskCommentModel.created_at > TaskReadStatusModel.last_read_at
                        )
                    )
                )
                .group_by(TaskCommentModel.task_id)
            )
            unread_res = await session.execute(unread_stmt)
            for row in unread_res.all():
                unread_map[row[0]] = row[1]

        avatar_cache: dict[str, str | None] = {}
        items = []
        for t in tasks:
            items.append(
                await TaskService._to_response(
                    session,
                    t,
                    owner_id,
                    unread_map=unread_map,
                    my_access_levels=my_access_levels,
                    avatar_cache=avatar_cache
                )
            )

        total_pages = math.ceil(total / limit) if limit > 0 else 1
        return PaginatedResponse[TaskResponse](
            items=items,
            total=total,
            page=page,
            pages=total_pages
        )

    @staticmethod
    async def get_task_by_id(session: AsyncSession, task_id: UUID, user_id: UUID = None, owner_id: UUID = None) -> TaskResponse:
        u_id = user_id or owner_id
        stmt = (
            select(TaskModel)
            .options(
                selectinload(TaskModel.owner),
                selectinload(TaskModel.collaborators).selectinload(TaskCollaboratorModel.user)
            )
            .where(TaskModel.id == task_id, TaskModel.deleted_at == None)
        )
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.owner_id != u_id:
            collab = next((c for c in task.collaborators if c.user_id == u_id), None)
            if not collab:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        return await TaskService._to_response(session, task, u_id)

    @staticmethod
    async def update_task(session: AsyncSession, task_id: UUID, task_in: TaskUpdate, user_id: UUID = None, owner_id: UUID = None) -> TaskResponse:
        u_id = user_id or owner_id
        stmt = select(TaskModel).where(TaskModel.id == task_id, TaskModel.deleted_at == None)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.owner_id != u_id:
            collab_stmt = select(TaskCollaboratorModel).where(
                and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id == u_id)
            )
            collab_res = await session.execute(collab_stmt)
            collab = collab_res.scalar_one_or_none()

            if not collab or _str(collab.access_level) != "full_access":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only task owner or co-owner with full access can edit full task details")

        task.title_encrypted = encrypt_field(task_in.title)
        task.title_index = compute_hmac_index(task_in.title)

        task.description_encrypted = encrypt_field(task_in.description) if task_in.description else None
        task.description_index = compute_hmac_index(task_in.description) if task_in.description else None

        task.priority = task_in.priority
        task.completed = task_in.completed
        task.due_date = task_in.due_date
        task.updated_at = datetime.now(timezone.utc)

        await TaskService.record_history(session, task_id, u_id, "updated", f"Task updated: '{task_in.title}'")
        await session.commit()
        await session.refresh(task)
        return await TaskService._to_response(session, task, u_id)

    @staticmethod
    async def update_task_status(session: AsyncSession, task_id: UUID, status_in: TaskStatusUpdate, user_id: UUID = None, owner_id: UUID = None) -> TaskResponse:
        u_id = user_id or owner_id
        stmt = select(TaskModel).where(TaskModel.id == task_id, TaskModel.deleted_at == None)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.owner_id != u_id:
            collab_stmt = select(TaskCollaboratorModel).where(
                and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id == u_id)
            )
            collab_res = await session.execute(collab_stmt)
            if not collab_res.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        task.completed = status_in.completed
        task.updated_at = datetime.now(timezone.utc)

        action_str = "status_changed"
        await TaskService.record_history(session, task_id, u_id, action_str, f"Status changed to {status_in.completed}")
        await session.commit()
        await session.refresh(task)

        target_ids = set()
        if task.owner_id != u_id:
            target_ids.add(str(task.owner_id))

        c_stmt = select(TaskCollaboratorModel.user_id).where(
            and_(TaskCollaboratorModel.task_id == task_id, TaskCollaboratorModel.user_id != u_id)
        )
        c_res = await session.execute(c_stmt)
        for c_id in c_res.scalars().all():
            target_ids.add(str(c_id))

        plain_title = decrypt_field(task.title_encrypted) or "Task"
        for tid in target_ids:
            await connection_manager.send_personal_message(
                {
                    "type": "task_status_changed",
                    "task_id": str(task_id),
                    "task_title": plain_title,
                    "completed": status_in.completed
                },
                tid
            )

        return await TaskService._to_response(session, task, u_id)

    @staticmethod
    async def delete_task(session: AsyncSession, task_id: UUID, owner_id: UUID = None, user_id: UUID = None) -> None:
        u_id = owner_id or user_id
        stmt = select(TaskModel).where(TaskModel.id == task_id, TaskModel.deleted_at == None)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.owner_id != u_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only task owner can delete this task")

        task.deleted_at = datetime.now(timezone.utc)
        await session.commit()

    @staticmethod
    async def create_share_request(session: AsyncSession, task_id: UUID, owner_id: UUID, data: TaskShareCreate) -> TaskShareResponse:
        stmt = (
            select(TaskModel)
            .options(selectinload(TaskModel.owner))
            .where(TaskModel.id == task_id, TaskModel.deleted_at == None)
        )
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only task owner can initiate share or ownership transfer requests")

        t_stmt = select(UserModel).where(UserModel.username.ilike(data.target_username.strip()), UserModel.deleted_at == None)
        t_res = await session.execute(t_stmt)
        target_user = t_res.scalar_one_or_none()

        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User @{data.target_username} not found")

        if target_user.id == owner_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot share a task with yourself")

        passcode = f"{random.randint(100000, 999999)}"
        passcode_hash = get_passcode_hash(passcode)
        now = datetime.now(timezone.utc)

        owner_username = task.owner.username if (task and task.owner) else "Owner"
        target_username = target_user.username

        share_req = TaskShareRequestModel(
            id=uuid.uuid4(),
            task_id=task_id,
            owner_id=owner_id,
            target_user_id=target_user.id,
            access_level=data.access_level,
            passcode_hash=passcode_hash,
            status="pending",
            created_at=now
        )
        session.add(share_req)

        plain_title = decrypt_field(task.title_encrypted) or "Task"
        await TaskService.record_history(
            session,
            task_id,
            owner_id,
            "share_requested",
            f"Share request ({data.access_level}) sent to @{target_username}"
        )

        await session.commit()
        await session.refresh(share_req)

        share_payload = {
            "type": "task_share_requested",
            "request_id": str(share_req.id),
            "task_id": str(task.id),
            "task_title": plain_title,
            "owner_username": owner_username,
            "access_level": _str(share_req.access_level)
        }
        await connection_manager.send_personal_message(share_payload, str(target_user.id))
        await connection_manager.send_personal_message(share_payload, str(owner_id))

        return TaskShareResponse(
            id=share_req.id,
            task_id=task.id,
            task_title=plain_title,
            owner_id=owner_id,
            owner_username=owner_username,
            target_user_id=target_user.id,
            target_username=target_username,
            access_level=_str(share_req.access_level),
            passcode=passcode,
            status=_str(share_req.status),
            created_at=share_req.created_at
        )

    @staticmethod
    async def get_pending_share_requests(session: AsyncSession, user_id: UUID) -> list[TaskShareResponse]:
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
            plain_title = decrypt_field(req.task.title_encrypted) if req.task else "Task"
            results.append(
                TaskShareResponse(
                    id=req.id,
                    task_id=req.task_id,
                    task_title=plain_title,
                    owner_id=req.owner_id,
                    owner_username=req.owner.username if req.owner else "Owner",
                    target_user_id=req.target_user_id,
                    target_username=req.target_user.username if req.target_user else "User",
                    access_level=_str(req.access_level),
                    passcode=None,
                    status=_str(req.status),
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
            if not verify_passcode(passcode.strip(), req.passcode_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid passcode provided")

            req.status = "accepted"
            req.accepted_at = datetime.now(timezone.utc)

            if _str(req.access_level) == "transfer":
                old_owner_id = req.owner_id
                old_owner_name = req.owner.username if req.owner else "previous owner"
                new_owner_name = req.target_user.username if req.target_user else "new owner"
                req.task.owner_id = user_id

                del_collab = select(TaskCollaboratorModel).where(
                    and_(TaskCollaboratorModel.task_id == req.task_id, TaskCollaboratorModel.user_id == user_id)
                )
                del_res = await session.execute(del_collab)
                existing_c = del_res.scalar_one_or_none()
                if existing_c:
                    await session.delete(existing_c)

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
                    f"Ownership transferred from @{old_owner_name} to @{new_owner_name}."
                )
            else:
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
                    f"Joined task as {_str(req.access_level)} collaborator"
                )

            plain_title = decrypt_field(req.task.title_encrypted) if (req and req.task) else "Task"
            target_username = req.target_user.username if (req and req.target_user) else "User"
            task_id_str = str(req.task_id)
            owner_id_str = str(req.owner_id)

            await session.commit()

            await connection_manager.send_personal_message(
                {
                    "type": "task_share_responded",
                    "request_id": str(request_id),
                    "task_id": task_id_str,
                    "task_title": plain_title,
                    "action": action,
                    "target_username": target_username
                },
                owner_id_str
            )
            await connection_manager.send_personal_message(
                {
                    "type": "task_share_responded",
                    "request_id": str(request_id),
                    "task_id": task_id_str,
                    "task_title": plain_title,
                    "action": action
                },
                str(user_id)
            )

            return {"message": "Task share request accepted", "status": "accepted", "task_id": task_id_str}

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")

    @staticmethod
    async def get_task_history(session: AsyncSession, task_id: UUID, user_id: UUID) -> list[TaskHistoryResponse]:
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
                    details=decrypt_field(h.details),
                    created_at=h.created_at
                )
            )
        return results

    @staticmethod
    async def remove_collaborator(session: AsyncSession, task_id: UUID, owner_id: UUID, target_user_id: UUID) -> dict:
        stmt = select(TaskModel).where(TaskModel.id == task_id, TaskModel.deleted_at == None)
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
    async def get_task_comments(session: AsyncSession, task_id: UUID, user_id: UUID) -> list[TaskCommentResponse]:
        await TaskService.get_task_by_id(session, task_id, user_id)

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
            dec_avatar = decrypt_field(c.author.avatar_url) if (c.author and c.author.avatar_url) else None
            dec_content = decrypt_field(c.content_encrypted) or ""
            results.append(
                TaskCommentResponse(
                    id=c.id,
                    task_id=c.task_id,
                    user_id=c.user_id,
                    author_name=c.author.username if c.author else "Unknown",
                    author_avatar_url=dec_avatar,
                    content=dec_content,
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
        author_name = user.username if user else "Unknown"
        author_avatar = decrypt_field(user.avatar_url) if (user and user.avatar_url) else None

        task_stmt = (
            select(TaskModel)
            .options(selectinload(TaskModel.collaborators))
            .where(TaskModel.id == task_id, TaskModel.deleted_at == None)
        )
        task_res = await session.execute(task_stmt)
        task_db = task_res.scalar_one_or_none()

        target_ids = set()
        if task_db:
            if task_db.owner_id != user_id:
                target_ids.add(str(task_db.owner_id))
            for c in task_db.collaborators:
                if c.user_id != user_id:
                    target_ids.add(str(c.user_id))

        comment_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        clean_content = data.content.strip()
        comment = TaskCommentModel(
            id=comment_id,
            task_id=task_id,
            user_id=user_id,
            content_encrypted=encrypt_field(clean_content),
            content_index=compute_hmac_index(clean_content),
            created_at=now,
            updated_at=now
        )
        session.add(comment)

        preview = clean_content[:30] + ("..." if len(clean_content) > 30 else "")
        await TaskService.record_history(session, task_id, user_id, "comment_added", f"Comment added: '{preview}'")

        await session.commit()

        for tid in target_ids:
            await connection_manager.send_personal_message(
                {
                    "type": "task_comment_added",
                    "task_id": str(task_id),
                    "author_name": author_name
                },
                tid
            )

        return TaskCommentResponse(
            id=comment_id,
            task_id=task_id,
            user_id=user_id,
            author_name=author_name,
            author_avatar_url=author_avatar,
            content=clean_content,
            created_at=now,
            updated_at=now
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

        author_name = comment.author.username if comment.author else "Unknown"
        author_avatar = decrypt_field(comment.author.avatar_url) if (comment.author and comment.author.avatar_url) else None

        clean_content = data.content.strip()
        updated_at = datetime.now(timezone.utc)
        comment.content_encrypted = encrypt_field(clean_content)
        comment.content_index = compute_hmac_index(clean_content)
        comment.updated_at = updated_at

        await session.commit()

        return TaskCommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            user_id=comment.user_id,
            author_name=author_name,
            author_avatar_url=author_avatar,
            content=clean_content,
            created_at=comment.created_at,
            updated_at=updated_at
        )

    @staticmethod
    async def delete_task_comment(
        session: AsyncSession,
        task_id: UUID,
        comment_id: UUID,
        user_id: UUID
    ) -> None:
        task_stmt = select(TaskModel).where(TaskModel.id == task_id, TaskModel.deleted_at == None)
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
        task_stmt = select(TaskModel).where(TaskModel.owner_id == user_id, TaskModel.deleted_at == None)
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

            new_owner_collab = next((c for c in collaborators if _str(c.access_level) == "full_access"), None)
            if not new_owner_collab:
                new_owner_collab = collaborators[0]

            new_owner_id = new_owner_collab.user_id
            new_owner_name = new_owner_collab.user.username if new_owner_collab.user else "new owner"

            task.owner_id = new_owner_id
            await session.delete(new_owner_collab)

            await TaskService.record_history(
                session,
                task.id,
                new_owner_id,
                "ownership_transferred",
                f"Ownership automatically transferred to @{new_owner_name} due to account deletion of former owner @{old_owner_name}."
            )

            plain_title = decrypt_field(task.title_encrypted) or "Task"
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