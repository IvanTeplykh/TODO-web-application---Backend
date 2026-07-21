import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from mongomock_motor import AsyncMongoMockClient
from app.main import app
from app.core.database import db

@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(autouse=True)
async def mock_database():
    """
    Fixture overriding global database instance with an in-memory mock Motor client.
    Clears collections before each test to guarantee complete test isolation.
    """
    mock_client = AsyncMongoMockClient()
    mock_db = mock_client["test_todo_db"]
    
    db.client = mock_client
    db._db = mock_db
    
    # Disable connect/close side effects during lifespan
    db.connect_to_database = lambda: None
    db.close_database_connection = lambda: None

    yield mock_db

    # Clean collections after each test
    await mock_db["users"].delete_many({})
    await mock_db["tasks"].delete_many({})

@pytest_asyncio.fixture
async def async_client():
    """
    Async HTTP client for invoking FastAPI app endpoints during tests.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest_asyncio.fixture
async def authenticated_user(async_client):
    """
    Fixture creating a test user and returning user profile along with JWT auth header.
    """
    user_payload = {
        "username": "TestUser",
        "email": "testuser@example.com",
        "password": "Password123!"
    }
    
    # Register user
    reg_response = await async_client.post("/api/v1/auth/register", json=user_payload)
    assert reg_response.status_code == 201

    # Login to acquire token
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": user_payload["email"],
        "password": user_payload["password"]
    })
    assert login_response.status_code == 200
    token_data = login_response.json()
    access_token = token_data["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Fetch profile
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    user_profile = me_res.json()
    
    return {
        "user": user_profile,
        "token": access_token,
        "headers": headers,
        "raw": user_payload
    }
