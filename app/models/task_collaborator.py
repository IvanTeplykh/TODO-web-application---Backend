import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.user import GUID


class CollaboratorRoleEnum(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class AccessLevelEnum(str, enum.Enum):
    TRANSFER = "transfer"
    FULL_ACCESS = "full_access"
    STATUS_ONLY = "status_only"
    EDITOR = "editor"
    VIEWER = "viewer"


class RequestStatusEnum(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class TaskCollaboratorModel(Base):
    __tablename__ = "task_collaborators"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_collaborator"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    access_level: Mapped[str] = mapped_column(
        Enum(AccessLevelEnum, native_enum=False),
        default=AccessLevelEnum.STATUS_ONLY.value,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    task = relationship("TaskModel", back_populates="collaborators")
    user = relationship("UserModel", foreign_keys=[user_id])


class TaskShareRequestModel(Base):
    __tablename__ = "task_share_requests"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    access_level: Mapped[str] = mapped_column(
        Enum(AccessLevelEnum, native_enum=False),
        nullable=False
    )
    passcode_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(RequestStatusEnum, native_enum=False),
        default=RequestStatusEnum.PENDING.value,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task = relationship("TaskModel", back_populates="share_requests")
    owner = relationship("UserModel", foreign_keys=[owner_id])
    target_user = relationship("UserModel", foreign_keys=[target_user_id])


class TaskHistoryModel(Base):
    __tablename__ = "task_history"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    task = relationship("TaskModel", back_populates="history")
    actor = relationship("UserModel", foreign_keys=[actor_id])


class TaskCommentModel(Base):
    __tablename__ = "task_comments"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    content_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    content_index: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
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

    task = relationship("TaskModel", back_populates="comments")
    author = relationship("UserModel", foreign_keys=[user_id])


class TaskReadStatusModel(Base):
    __tablename__ = "task_read_statuses"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_user_read_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
