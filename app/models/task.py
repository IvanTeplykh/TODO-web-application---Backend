import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.models.base import Base
from app.models.user import GUID


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    title_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    title_index: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_index: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, index=True, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    owner = relationship("UserModel", backref=backref("tasks", passive_deletes=True))
    collaborators = relationship("TaskCollaboratorModel", back_populates="task", cascade="all, delete-orphan")
    share_requests = relationship("TaskShareRequestModel", back_populates="task", cascade="all, delete-orphan")
    history = relationship("TaskHistoryModel", back_populates="task", cascade="all, delete-orphan")
    comments = relationship("TaskCommentModel", back_populates="task", cascade="all, delete-orphan")
