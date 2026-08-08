from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.base import Base
import app.models.user
import app.models.task
import app.models.task_collaborator
import app.models.chat
import app.models.channel
import app.models.infrastructure


class Database:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    def connect_to_database(self, url: str | None = None):
        raw_url = url or settings.DATABASE_URL
        db_url = raw_url.strip().strip("'").strip('"')

        if not db_url:
            raise ValueError("[ERROR] DATABASE_URL is empty!")

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

        engine_kwargs = {
            "echo": False,
            "future": True,
            "connect_args": connect_args,
        }

        # Enable high-performance connection pooling for PostgreSQL (Railway/cloud deployment)
        if not db_url.startswith("sqlite"):
            engine_kwargs.update({
                "pool_pre_ping": True,     # Proactively test connections to eliminate dead connection drops
                "pool_size": 20,           # Keep pool of warm connections ready for instant reuse
                "max_overflow": 20,        # Allow temporary burst traffic without queuing
                "pool_recycle": 300,       # Recycle idle connections every 5 min to prevent proxy timeouts
                "pool_timeout": 30,        # Timeout waiting for pool connection
            })

        try:
            self.engine = create_async_engine(
                db_url,
                **engine_kwargs
            )
        except Exception as e:
            print(f"[ERROR] Could not parse DATABASE_URL: {e}")
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
                def sync_schema(sync_conn):
                    from sqlalchemy import inspect
                    inspector = inspect(sync_conn)
                    if inspector.has_table("users"):
                        cols = [c["name"] for c in inspector.get_columns("users")]
                        # If legacy columns ('email', 'password', 'email_hash') exist or 'email_encrypted' is missing,
                        # drop old MVP tables so metadata.create_all creates the Production Privacy-First schema
                        if "email" in cols or "email_encrypted" not in cols or "password_hash" not in cols:
                            print("[DB MIGRATION] Legacy schema detected. Dropping old tables to recreate Production Privacy-First schema...")
                            Base.metadata.drop_all(sync_conn)

                    Base.metadata.create_all(sync_conn)

                await conn.run_sync(sync_schema)

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
