from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import db, global_chat_db
from app.routers.auth import router as auth_router
from app.routers.tasks import router as tasks_router
from app.routers.users import router as users_router
from app.routers.chat import router as chat_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to main DB & global chat DB and create tables
    db.connect_to_database()
    await db.init_db()

    global_chat_db.connect_to_database()
    await global_chat_db.init_db()
    yield
    # Shutdown: Close database connections
    await db.close_database_connection()
    await global_chat_db.close_database_connection()

app = FastAPI(
    title="TODO Web Application Backend",
    description="FastAPI + Multi-Database (PostgreSQL + Isolated Global Chat DB) backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers under prefix '/api/v1'
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to TODO API. Access Swagger docs at /docs"}
