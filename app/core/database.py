from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
from app.models.base import Base
import app.models.user
import app.models.task
import app.models.chat
import app.models.global_chat
import app.models.channel
import app.models.task_collaborator

from sqlalchemy import text

class Database:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    def connect_to_database(self, url: str | None = None):
        raw_url = url or settings.DATABASE_URL
        db_url = raw_url.strip().strip("'").strip('"')

        if not db_url:
            raise ValueError("[ERROR] DATABASE_URL is empty! Please set DATABASE_URL variable in Railway settings.")

        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://"):
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

        try:
            self.engine = create_async_engine(
                db_url,
                echo=False,
                connect_args=connect_args,
                future=True
            )
        except Exception as e:
            safe_prefix = db_url[:20] if len(db_url) > 20 else db_url
            print(f"[ERROR] Could not parse DATABASE_URL (prefix: '{safe_prefix}'): {e}")
            raise
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

            table_sqls = [
                "ALTER TABLE users ADD COLUMN chat_retention_days INTEGER DEFAULT 180;",
                "ALTER TABLE users ADD COLUMN email_hash VARCHAR(64);",
                "ALTER TABLE task_share_requests ALTER COLUMN passcode TYPE VARCHAR(255);",
                "CREATE INDEX IF NOT EXISTS ix_users_email_hash ON users (email_hash);",
                """
                CREATE TABLE IF NOT EXISTS task_collaborators (
                    id UUID PRIMARY KEY,
                    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    access_level VARCHAR(20) NOT NULL DEFAULT 'status_only',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_task_collaborator UNIQUE (task_id, user_id)
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS task_share_requests (
                    id UUID PRIMARY KEY,
                    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    target_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    access_level VARCHAR(20) NOT NULL,
                    passcode VARCHAR(255) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS task_history (
                    id UUID PRIMARY KEY,
                    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    action VARCHAR(50) NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS task_comments (
                    id UUID PRIMARY KEY,
                    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS task_read_statuses (
                    id UUID PRIMARY KEY,
                    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    last_read_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_task_user_read_status UNIQUE (task_id, user_id)
                );
                """
            ]
            for sql_stmt in table_sqls:
                try:
                    async with self.engine.begin() as conn:
                        await conn.execute(text(sql_stmt))
                except Exception:
                    pass

    async def close_database_connection(self):
        if self.engine:
            await self.engine.dispose()

db = Database()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db.session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
