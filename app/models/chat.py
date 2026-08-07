import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.task_collaborator import RequestStatusEnum
from app.models.user import GUID


class ChatRequestModel(Base):
    __tablename__ = "chat_requests"
    __table_args__ = (
        UniqueConstraint("requester_id", "recipient_id", name="uq_requester_recipient"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
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

    requester = relationship("UserModel", foreign_keys=[requester_id])
    recipient = relationship("UserModel", foreign_keys=[recipient_id])


class ChatMessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    sender_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("channels.id", ondelete="CASCADE"),
        index=True,
        nullable=True
    )
    content_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    content_index: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    sender = relationship("UserModel", foreign_keys=[sender_id])
    recipient_user = relationship("UserModel", foreign_keys=[recipient_user_id])
    channel = relationship("ChannelModel", foreign_keys=[channel_id])
