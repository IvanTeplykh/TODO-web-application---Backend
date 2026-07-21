import pytest

@pytest.mark.asyncio
async def test_update_profile_info(async_client, authenticated_user):
    headers = authenticated_user["headers"]

    update_payload = {
        "username": "UpdatedUsername",
        "avatar_url": "https://example.com/avatar.png"
    }

    response = await async_client.put("/api/v1/users/me", json=update_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "UpdatedUsername"
    assert data["avatar_url"] == "https://example.com/avatar.png"

    # Verify /auth/me returns updated details
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "UpdatedUsername"

@pytest.mark.asyncio
async def test_verify_password(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    correct_password = authenticated_user["raw"]["password"]

    # Verify correct password
    res1 = await async_client.post("/api/v1/users/verify-password", json={"password": correct_password}, headers=headers)
    assert res1.status_code == 200
    assert res1.json() == {"valid": True}

    # Verify incorrect password
    res2 = await async_client.post("/api/v1/users/verify-password", json={"password": "WrongPassword123!"}, headers=headers)
    assert res2.status_code == 200
    assert res2.json() == {"valid": False}

@pytest.mark.asyncio
async def test_change_password_success_and_login_with_new_password(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    old_password = authenticated_user["raw"]["password"]
    email = authenticated_user["raw"]["email"]
    new_password = "BrandNewPassword456!"

    # Change password
    change_res = await async_client.post("/api/v1/users/change-password", json={
        "current_password": old_password,
        "new_password": new_password
    }, headers=headers)
    assert change_res.status_code == 200
    assert change_res.json() == {"message": "Password changed successfully"}

    # Attempt login with old password -> should fail with 401
    old_login = await async_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": old_password
    })
    assert old_login.status_code == 401

    # Login with new password -> should succeed
    new_login = await async_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": new_password
    })
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()

@pytest.mark.asyncio
async def test_change_password_incorrect_current_password(async_client, authenticated_user):
    headers = authenticated_user["headers"]

    change_res = await async_client.post("/api/v1/users/change-password", json={
        "current_password": "InvalidCurrentPassword",
        "new_password": "NewPassword123!"
    }, headers=headers)
    assert change_res.status_code == 400
    assert "Incorrect current password" in change_res.json()["detail"]

@pytest.mark.asyncio
async def test_change_password_same_password_error(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    same_password = authenticated_user["raw"]["password"]

    change_res = await async_client.post("/api/v1/users/change-password", json={
        "current_password": same_password,
        "new_password": same_password
    }, headers=headers)
    assert change_res.status_code == 400
    assert "New password must be different" in change_res.json()["detail"]
