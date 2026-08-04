import uuid
import math
import hashlib
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
from fastapi import HTTPException, status
from app.core.database import db
from app.schemas.task import TaskCreate, TaskUpdate, TaskStatusUpdate, TaskResponse
from app.utils.pagination import PaginatedResponse

def compute_hash(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

class TaskService:
    @staticmethod
    def _to_response(doc: dict) -> TaskResponse:
        t_hash = doc.get("title_hash") or compute_hash(doc.get("title"))
        d_hash = doc.get("description_hash") if "description_hash" in doc else compute_hash(doc.get("description"))

        return TaskResponse(
            id=UUID(doc["_id"]),
            title=doc["title"],
            title_hash=t_hash,
            completed=doc["completed"],
            priority=doc["priority"],
            description=doc.get("description"),
            description_hash=d_hash,
            due_date=doc.get("due_date"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            owner_id=UUID(doc["owner_id"])
        )

    @staticmethod
    async def create_task(task_in: TaskCreate, owner_id: UUID) -> TaskResponse:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        t_hash = compute_hash(task_in.title)
        d_hash = compute_hash(task_in.description)

        task_doc = {
            "_id": task_id,
            "title": task_in.title,
            "title_hash": t_hash,
            "completed": False,
            "priority": task_in.priority,
            "description": task_in.description,
            "description_hash": d_hash,
            "due_date": task_in.due_date,
            "created_at": now,
            "updated_at": now,
            "owner_id": str(owner_id)
        }
        
        await db.tasks_collection.insert_one(task_doc)
        return TaskService._to_response(task_doc)

    @staticmethod
    async def get_tasks(
        owner_id: UUID,
        page: int,
        limit: int,
        status_filter: str,
        search: str | None,
        sort: str,
        order: str
    ) -> PaginatedResponse[TaskResponse]:
        query = {"owner_id": str(owner_id)}
        
        if status_filter == "done":
            query["completed"] = True
        elif status_filter == "undone":
            query["completed"] = False
        elif status_filter == "overdue":
            query["completed"] = False
            query["due_date"] = {"$ne": None, "$lt": datetime.now(timezone.utc)}
        
        if search:
            query["title"] = {"$regex": search, "$options": "i"}
            
        total = await db.tasks_collection.count_documents(query)
        
        sort_direction = 1 if order == "asc" else -1
        allowed_sort_fields = {"priority", "created_at", "updated_at", "title", "completed", "due_date"}
        sort_field = sort if sort in allowed_sort_fields else "created_at"
        
        skip = (page - 1) * limit
        
        if sort_field == "due_date":
            pipeline = [
                {"$match": query},
                {
                    "$addFields": {
                        "has_due_date": {"$cond": [{"$ne": ["$due_date", None]}, 1, 0]}
                    }
                },
                {"$sort": {"has_due_date": -1, "due_date": sort_direction}},
                {"$skip": skip},
                {"$limit": limit}
            ]
            cursor = db.tasks_collection.aggregate(pipeline)
            task_docs = await cursor.to_list(length=limit)
        else:
            cursor = db.tasks_collection.find(query).sort(sort_field, sort_direction).skip(skip).limit(limit)
            task_docs = await cursor.to_list(length=limit)
        
        pages = math.ceil(total / limit) if total > 0 else 1
        items = [TaskService._to_response(doc) for doc in task_docs]
        
        return PaginatedResponse[TaskResponse](
            items=items,
            total=total,
            page=page,
            pages=pages
        )

    @staticmethod
    async def get_task_by_id(task_id: UUID, owner_id: UUID) -> TaskResponse:
        task = await db.tasks_collection.find_one({"_id": str(task_id)})
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task["owner_id"] != str(owner_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this task"
            )
            
        return TaskService._to_response(task)

    @staticmethod
    async def update_task(task_id: UUID, task_in: TaskUpdate, owner_id: UUID) -> TaskResponse:
        task = await db.tasks_collection.find_one({"_id": str(task_id)})
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task["owner_id"] != str(owner_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this task"
            )
            
        t_hash = compute_hash(task_in.title)
        d_hash = compute_hash(task_in.description)

        update_data = {
            "title": task_in.title,
            "title_hash": t_hash,
            "priority": task_in.priority,
            "completed": task_in.completed,
            "description": task_in.description,
            "description_hash": d_hash,
            "due_date": task_in.due_date,
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.tasks_collection.update_one({"_id": str(task_id)}, {"$set": update_data})
        updated_task = await db.tasks_collection.find_one({"_id": str(task_id)})
        return TaskService._to_response(updated_task)

    @staticmethod
    async def update_task_status(task_id: UUID, status_in: TaskStatusUpdate, owner_id: UUID) -> TaskResponse:
        task = await db.tasks_collection.find_one({"_id": str(task_id)})
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task["owner_id"] != str(owner_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this task"
            )
            
        update_data = {
            "completed": status_in.completed,
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.tasks_collection.update_one({"_id": str(task_id)}, {"$set": update_data})
        updated_task = await db.tasks_collection.find_one({"_id": str(task_id)})
        return TaskService._to_response(updated_task)

    @staticmethod
    async def delete_task(task_id: UUID, owner_id: UUID) -> None:
        task = await db.tasks_collection.find_one({"_id": str(task_id)})
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task["owner_id"] != str(owner_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this task"
            )
            
        await db.tasks_collection.delete_one({"_id": str(task_id)})
