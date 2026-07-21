# TODO Web Application - Backend

This project serves as the server-side (Backend) component of a web application designed for task management (TODO). It delivers a high-performance RESTful API with asynchronous request processing, JWT-based user authentication, MongoDB integration, and comprehensive data schema validation.

---

## Tech Stack

- **Programming Language**: Python 3.10+
- **Web Framework**: FastAPI - Asynchronous, high-performance web framework for building REST APIs.
- **Async DB Driver**: Motor - Official asynchronous MongoDB driver for Python.
- **Database**: MongoDB (Supports both local installations and MongoDB Atlas cloud deployment).
- **Validation and Serialization**: Pydantic v2 & Pydantic Settings - Strict validation for request/response schemas and environment configurations.
- **Authentication & Security**:
  - JWT (JSON Web Tokens via python-jose) - Access token issuing and verification.
  - Bcrypt & Passlib - Secure password hashing and verification algorithms.
- **ASGI Server**: Uvicorn - Lightning-fast ASGI server implementation.

---

## Architecture and Project Structure

The project follows a modular architecture separating concerns cleanly across modules:

- `app/core` - Database connectivity (`database.py`), application configuration (`config.py`), and security primitives (`security.py`).
- `app/dependencies` - FastAPI dependency injection for JWT token verification and current user retrieval (`auth.py`).
- `app/routers` - REST API controllers:
  - `auth.py` - User registration, authentication, logout, and email verification.
  - `tasks.py` - Task CRUD operations, filtering, pagination, and status toggles.
  - `users.py` - Profile management and password updates.
- `app/services` - Core business logic encapsulates (`auth_service.py`, `task_service.py`).
- `app/schemas` - Pydantic models for request validation and response formatting.
- `app/models` - Internal database entity data structures.
- `app/utils` - Utility functions (pagination response formatters).

---

## API Endpoints & Functionality

### 1. Authentication (`/api/v1/auth`)
- `GET /api/v1/auth/check-email?email=...` - Checks whether an email address is already registered in the system.
- `POST /api/v1/auth/register` - Registers a new user (verifies email uniqueness, hashes password).
- `POST /api/v1/auth/login` - Authenticates user credentials and returns a JWT Access Token.
- `GET /api/v1/auth/me` - Retrieves profile data for the authenticated user.
- `POST /api/v1/auth/logout` - Invalidates/logs out current user session.

### 2. Task Management (`/api/v1/tasks`)
- `POST /api/v1/tasks` - Creates a new task (fields: `title` up to 100 chars, `description`, `due_date`, `priority` between 1 and 10).
- `GET /api/v1/tasks` - Retrieves a list of tasks owned by the user with support for:
  - Pagination: `page` (default 1), `limit` (1 to 500).
  - Status Filtering: `status` (`all`, `done`, `undone`, `overdue`).
  - Search: `search` (case-insensitive substring match on task title).
  - Sorting: `sort` (`created_at`, `due_date`, `priority`), `order` (`asc`, `desc`).
- `GET /api/v1/tasks/{task_id}` - Fetches a specific task by its UUID.
- `PUT /api/v1/tasks/{task_id}` - Updates all details of a task.
- `PATCH /api/v1/tasks/{task_id}/status` - Toggles task completion status (`is_completed`).
- `DELETE /api/v1/tasks/{task_id}` - Deletes a task by UUID.

### 3. User Profile (`/api/v1/users`)
- `PUT /api/v1/users/me` - Updates user `username` and `avatar_url`.
- `POST /api/v1/users/change-password` - Updates password after verifying current password correctness and ensuring new password differs from current.
- `POST /api/v1/users/verify-password` - Validates whether the supplied password matches the current user's password.

### 4. Interactive Documentation
FastAPI automatically generates interactive API documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Environment Variables

Create a `.env` file in the root directory of the backend with the following configuration:

```env
SECRET_KEY=your_jwt_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/dbname
DATABASE_NAME=todo_app_database
```

---

## Quick Start

### 1. Create and Activate Virtual Environment

On Windows (PowerShell / CMD):
```bash
python -m venv .venv
.venv\Scripts\activate
```

On macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Development Server
```bash
uvicorn app.main:app --reload
```
The server will start at `http://localhost:8000`.
