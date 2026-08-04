from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.models.base import Base
import app.models.user
import app.models.task
import app.models.chat
import app.models.global_chat

class Database:
    def __init__(self, get_default_url_fn):
        self.get_default_url_fn = get_default_url_fn
        self.engine = None
        self.session_factory = None

    def connect_to_database(self, url: str | None = None):
        db_url = url or self.get_default_url_fn()
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        if "asyncpg" in db_url and "sslmode=" in db_url:
            db_url = (
                db_url.replace("sslmode=require", "ssl=require")
                .replace("sslmode=prefer", "ssl=prefer")
                .replace("sslmode=allow", "ssl=allow")
                .replace("sslmode=disable", "ssl=disable")
            )

        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        self.engine = create_async_engine(
            db_url,
            echo=False,
            connect_args=connect_args,
            future=True
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )

    async def init_db(self):
        if self.engine:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    async def close_database_connection(self):
        if self.engine:
            await self.engine.dispose()

db = Database(lambda: settings.DATABASE_URL)
global_chat_db = Database(lambda: settings.GLOBAL_CHAT_DATABASE_URL)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db.session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_global_chat_db() -> AsyncGenerator[AsyncSession, None]:
    async with global_chat_db.session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
