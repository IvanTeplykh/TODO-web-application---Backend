import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.user import GUID


class ChannelModel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    owner = relationship("UserModel", foreign_keys=[owner_id])
    members = relationship("ChannelMemberModel", back_populates="channel", cascade="all, delete-orphan")
    messages = relationship("ChannelMessageModel", back_populates="channel", cascade="all, delete-orphan")

class ChannelMemberModel(Base):
    __tablename__ = "channel_members"
    __table_args__ = (
        UniqueConstraint("channel_id", "user_id", name="uq_channel_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("channels.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False) # owner, admin, member
    status: Mapped[str] = mapped_column(String(20), default="accepted", server_default="accepted", nullable=False) # pending, accepted
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    channel = relationship("ChannelModel", back_populates="members")
    user = relationship("UserModel", foreign_keys=[user_id])

class ChannelMessageModel(Base):
    __tablename__ = "channel_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("channels.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    channel = relationship("ChannelModel", back_populates="messages")
    sender = relationship("UserModel", foreign_keys=[sender_id])
