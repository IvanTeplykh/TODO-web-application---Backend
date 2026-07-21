import pytest

@pytest.mark.asyncio
async def test_check_email_exists_and_not_exists(async_client):
    # Check email when non-existent
    res1 = await async_client.get("/api/v1/auth/check-email", params={"email": "newuser@example.com"})
    assert res1.status_code == 200
    assert res1.json() == {"exists": False}

    # Register user
    reg_payload = {
        "username": "ExistingUser",
        "email": "newuser@example.com",
        "password": "Password123!"
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    assert reg_res.json() == {"message": "User created successfully"}

    # Check email now
    res2 = await async_client.get("/api/v1/auth/check-email", params={"email": "newuser@example.com"})
    assert res2.status_code == 200
    assert res2.json() == {"exists": True}

@pytest.mark.asyncio
async def test_register_user_success(async_client):
    payload = {
        "username": "JohnDoe",
        "email": "john@example.com",
        "password": "SecurePassword123!"
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json() == {"message": "User created successfully"}

@pytest.mark.asyncio
async def test_register_duplicate_email_fails(async_client):
    payload = {
        "username": "UserOne",
        "email": "duplicate@example.com",
        "password": "Password123!"
    }
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/v1/auth/register", json={
        "username": "UserTwo",
        "email": "duplicate@example.com",
        "password": "Password123!"
    })
    assert res2.status_code == 400
    assert "User with this email already exists" in res2.json()["detail"]

@pytest.mark.asyncio
async def test_login_success(async_client):
    # Register user
    reg_payload = {
        "username": "LoginUser",
        "email": "login@example.com",
        "password": "MySecretPassword123"
    }
    await async_client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_payload = {
        "email": "login@example.com",
        "password": "MySecretPassword123"
    }
    login_res = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_invalid_credentials(async_client):
    login_res = await async_client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "WrongPassword"
    })
    assert login_res.status_code == 401
    assert "Invalid email or password" in login_res.json()["detail"]

@pytest.mark.asyncio
async def test_get_me_unauthorized(async_client):
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_me_authorized(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == authenticated_user["user"]["email"]

@pytest.mark.asyncio
async def test_logout_authorized(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    response = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out successfully"}
