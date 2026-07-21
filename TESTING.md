# Backend Testing Documentation & Instructions

This document provides a comprehensive guide to the automated testing suite implemented for the TODO Web Application Backend (Python / FastAPI). It details the testing methodology, directory structure, individual test cases, and instructions for running and extending the test suite.

---

## 1. Overview & Testing Approach

The testing framework uses **Pytest**, **Pytest-Asyncio**, **HTTPX**, and **MongoMock-Motor**.

### Key Testing Characteristics:
- **In-Memory Isolated Database**: Tests execute against `mongomock_motor.AsyncMongoMockClient`. No live MongoDB instance or network database connection is required.
- **Automatic Cleanup**: Database state is cleared automatically before and after each test case to prevent side effects or inter-test pollution.
- **Asynchronous Execution**: Asynchronous FastAPI endpoints are tested directly using `httpx.AsyncClient` with `ASGITransport`.
- **Zero Production Risk**: Mocked database fixtures guarantee that running tests never mutates development or production databases.

---

## 2. Test Environment Setup & Configuration

### Prerequisites
Make sure Python 3.10+ and virtual environment `.venv` are configured.

### Dependencies
Required testing packages listed in `requirements.txt`:
- `pytest>=8.0.0` - Core test runner and framework.
- `pytest-asyncio>=0.23.0` - Async test support for coroutines.
- `httpx>=0.27.0` - Asynchronous HTTP client for FastAPI ASGI invocation.
- `mongomock-motor>=0.0.3` - In-memory mock driver for Motor MongoDB client.

### Pytest Configuration (`pytest.ini`)
The root directory includes a `pytest.ini` file configuring automatic import paths and asyncio loop scopes:

```ini
[pytest]
pythonpath = .
asyncio_mode = auto
asyncio_default_fixture_loop_scope = session
```

---

## 3. Test Directory Structure & Files

The testing directory is structured as follows:

```
TODO-web-application---Backend/
|-- tests/
|   |-- conftest.py            # Global fixtures, database mocks, HTTP client
|   |-- test_auth.py           # Regression tests for Authentication API
|   |-- test_tasks.py          # Regression tests for Task Management API & Isolation
|   |-- test_users.py          # Regression tests for Profile & Password Security
|   |-- test_e2e_user_flow.py  # End-to-End User Flow integration test
|-- pytest.ini                 # Pytest configuration file
|-- TESTING.md                 # Detailed testing documentation (this file)
```

---

## 4. Test Suites & Individual Test Cases Description

### A. Shared Fixtures (`tests/conftest.py`)
- `mock_database`: Autouse fixture that substitutes `app.core.database.db` with `AsyncMongoMockClient`, disables lifespan database connection hooks, and wipes database collections after each test.
- `async_client`: Provides an `httpx.AsyncClient` instance wired to the FastAPI application.
- `authenticated_user`: Creates a temporary user, authenticates via `/api/v1/auth/login`, fetches user details via `/api/v1/auth/me`, and returns valid authorization headers (`Authorization: Bearer <token>`).

---

### B. Authentication API Regression (`tests/test_auth.py`)

1. `test_check_email_exists_and_not_exists`
   - Verifies `/api/v1/auth/check-email` returns `{"exists": False}` for unregistered email.
   - Registers a new user with that email.
   - Verifies `/api/v1/auth/check-email` now returns `{"exists": True}`.

2. `test_register_user_success`
   - Sends valid user credentials to `/api/v1/auth/register`.
   - Asserts HTTP 201 status code and `{"message": "User created successfully"}` response.

3. `test_register_duplicate_email_fails`
   - Registers a user with email `duplicate@example.com`.
   - Attempts registering a second user with the same email.
   - Asserts HTTP 400 Bad Request with error detail `"User with this email already exists"`.

4. `test_login_success`
   - Registers a user and authenticates via `/api/v1/auth/login`.
   - Asserts HTTP 200 OK and presence of valid `access_token` and `token_type: "bearer"`.

5. `test_login_invalid_credentials`
   - Attempts login with invalid email or password.
   - Asserts HTTP 401 Unauthorized with error detail `"Invalid email or password"`.

6. `test_get_me_unauthorized`
   - Requests `/api/v1/auth/me` without Authorization header.
   - Asserts HTTP 401 Unauthorized.

7. `test_get_me_authorized`
   - Requests `/api/v1/auth/me` using valid Bearer token.
   - Asserts HTTP 200 OK and returns correct email and user metadata.

8. `test_logout_authorized`
   - Sends POST request to `/api/v1/auth/logout` with Bearer token.
   - Asserts HTTP 200 OK and response `{"message": "Logged out successfully"}`.

---

### C. Task Management API & Data Isolation (`tests/test_tasks.py`)

1. `test_create_task_success`
   - Creates a task with title, description, priority (1-10), and due date.
   - Asserts HTTP 201 Created, assigned UUID `id`, and default `completed: False` state.

2. `test_create_task_validation_errors`
   - Tests schema validation rules:
     - Title exceeding 100 characters -> HTTP 422 Unprocessable Entity.
     - Priority out of bounds (> 10) -> HTTP 422 Unprocessable Entity.

3. `test_get_tasks_pagination_search_filtering`
   - Creates multiple tasks with different priorities and titles.
   - Marks one task as completed.
   - Tests `GET /api/v1/tasks` with default pagination (`total == 3`).
   - Tests filtering by status (`status=done` returns only completed task).
   - Tests title search query (`search=Beta` returns matching task).

4. `test_update_task_details`
   - Updates task title, priority, description, completion status, and due date via `PUT /api/v1/tasks/{id}`.
   - Asserts HTTP 200 OK and updated field values.

5. `test_delete_task`
   - Deletes a task via `DELETE /api/v1/tasks/{id}` -> HTTP 204 No Content.
   - Subsequent `GET /api/v1/tasks/{id}` request returns HTTP 404 Not Found.

6. `test_task_data_isolation_between_users`
   - User 1 creates a private task.
   - User 2 registers and attempts accessing User 1's task (`GET` and `DELETE`).
   - Asserts User 2 receives **HTTP 403 Forbidden** and User 2's task list total remains 0.

---

### D. User Profile & Password Security (`tests/test_users.py`)

1. `test_update_profile_info`
   - Updates user `username` and `avatar_url` via `PUT /api/v1/users/me`.
   - Asserts HTTP 200 OK and verifies profile change persists in `/auth/me`.

2. `test_verify_password`
   - Validates `/api/v1/users/verify-password` with correct password -> `{"valid": True}`.
   - Validates with wrong password -> `{"valid": False}`.

3. `test_change_password_success_and_login_with_new_password`
   - Changes password via `/api/v1/users/change-password`.
   - Verifies login attempt using old password fails with HTTP 401.
   - Verifies login attempt using new password succeeds with HTTP 200 and issues new token.

4. `test_change_password_incorrect_current_password`
   - Attempts password change supplying wrong current password -> HTTP 400 Bad Request.

5. `test_change_password_same_password_error`
   - Attempts setting new password equal to current password -> HTTP 400 Bad Request.

---

### E. End-to-End (E2E) User Flow (`tests/test_e2e_user_flow.py`)

1. `test_complete_e2e_user_journey`
   - Single cohesive test simulating a full client lifecycle:
     - Check email -> Register user `AlexDev` -> Login and obtain JWT token.
     - Create 3 tasks with varying priorities and deadlines.
     - Search tasks by keyword and filter by completion status.
     - Toggle task completion status.
     - Update user profile username to `Alex Senior Dev`.
     - Verify current password and change password to `SuperSecretNewPassword99!`.
     - Re-authenticate with new password.
     - Delete completed task and verify remaining task list count.
     - Logout user session.

---

## 5. How to Run Tests

### Running Full Test Suite
Open terminal in the backend directory (`TODO-web-application---Backend`) and execute:

```bash
# Run all tests with verbose output
pytest -v
```

### Running Specific Test Files
To run a specific test module:

```bash
pytest tests/test_auth.py -v
pytest tests/test_tasks.py -v
pytest tests/test_users.py -v
pytest tests/test_e2e_user_flow.py -v
```

### Running a Specific Test Function
```bash
pytest tests/test_e2e_user_flow.py -k test_complete_e2e_user_journey -v
```

### Running with Output Capture Disabled (Print Statements Visible)
```bash
pytest -v -s
```

---

## 6. How to Add New Tests

When adding new endpoints or features to the backend:
1. Identify whether the feature belongs to Auth, Tasks, Users, or a new module.
2. Create a new test function prefixed with `test_` inside the corresponding file under `tests/`.
3. Annotate the function with `@pytest.mark.asyncio`.
4. Inject `async_client` (and `authenticated_user` if authentication is required).
5. Run `pytest -v` to ensure the new test passes without affecting existing suites.
