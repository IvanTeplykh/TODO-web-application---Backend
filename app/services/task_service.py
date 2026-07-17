import uuid
import math
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException, status
from app.core.database import db
from app.schemas.task import TaskCreate, TaskUpdate, TaskStatusUpdate, TaskResponse
from app.utils.pagination import PaginatedResponse

class TaskService:
    @staticmethod
    async def create_task(task_in: TaskCreate, owner_id: UUID) -> TaskResponse:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        task_doc = {
            "_id": task_id,
            "title": task_in.title,
            "completed": False,
            "priority": task_in.priority,
            "description": task_in.description,
            "due_date": task_in.due_date,
            "created_at": now,
            "updated_at": now,
            "owner_id": str(owner_id)
        }
        
        await db.tasks_collection.insert_one(task_doc)
        
        return TaskResponse(
            id=UUID(task_doc["_id"]),
            title=task_doc["title"],
            completed=task_doc["completed"],
            priority=task_doc["priority"],
            description=task_doc.get("description"),
            due_date=task_doc.get("due_date"),
            created_at=task_doc["created_at"],
            updated_at=task_doc["updated_at"],
            owner_id=UUID(task_doc["owner_id"])
        )

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
        
        if search:
            query["title"] = {"$regex": search, "$options": "i"}
            
        total = await db.tasks_collection.count_documents(query)
        
        sort_direction = 1 if order == "asc" else -1
        # Prevent injection or incorrect fields by defaulting to created_at
        allowed_sort_fields = {"priority", "created_at", "updated_at", "title", "completed"}
        sort_field = sort if sort in allowed_sort_fields else "created_at"
        
        skip = (page - 1) * limit
        cursor = db.tasks_collection.find(query).sort(sort_field, sort_direction).skip(skip).limit(limit)
        task_docs = await cursor.to_list(length=limit)
        
        pages = math.ceil(total / limit) if total > 0 else 1
        
        items = [
            TaskResponse(
                id=UUID(doc["_id"]),
                title=doc["title"],
                completed=doc["completed"],
                priority=doc["priority"],
                description=doc.get("description"),
                due_date=doc.get("due_date"),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
                owner_id=UUID(doc["owner_id"])
            )
            for doc in task_docs
        ]
        
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
            
        return TaskResponse(
            id=UUID(task["_id"]),
            title=task["title"],
            completed=task["completed"],
            priority=task["priority"],
            description=task.get("description"),
            due_date=task.get("due_date"),
            created_at=task["created_at"],
            updated_at=task["updated_at"],
            owner_id=UUID(task["owner_id"])
        )

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
            
        update_data = {
            "title": task_in.title,
            "priority": task_in.priority,
            "completed": task_in.completed,
            "description": task_in.description,
            "due_date": task_in.due_date,
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.tasks_collection.update_one({"_id": str(task_id)}, {"$set": update_data})
        
        updated_task = await db.tasks_collection.find_one({"_id": str(task_id)})
        return TaskResponse(
            id=UUID(updated_task["_id"]),
            title=updated_task["title"],
            completed=updated_task["completed"],
            priority=updated_task["priority"],
            description=updated_task.get("description"),
            due_date=updated_task.get("due_date"),
            created_at=updated_task["created_at"],
            updated_at=updated_task["updated_at"],
            owner_id=UUID(updated_task["owner_id"])
        )

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
        return TaskResponse(
            id=UUID(updated_task["_id"]),
            title=updated_task["title"],
            completed=updated_task["completed"],
            priority=updated_task["priority"],
            description=updated_task.get("description"),
            due_date=updated_task.get("due_date"),
            created_at=updated_task["created_at"],
            updated_at=updated_task["updated_at"],
            owner_id=UUID(updated_task["owner_id"])
        )

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
