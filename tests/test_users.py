import pytest
from uuid import UUID
from app.services.chat_service import chat_service
from app.schemas.chat import MessageCreate

@pytest.mark.asyncio
async def test_update_profile_info(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    user_id = UUID(authenticated_user["user"]["id"])

    # Create a message first
    from app.core.database import db
    async with db.session_factory() as session:
        await chat_service.create_message(
            session=session,
            sender_id=user_id,
            data=MessageCreate(recipient_id="global", content="Test Message Before Profile Update")
        )

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

    # Verify historical messages in chat now reflect updated username & avatar
    messages_res = await async_client.get("/api/v1/chat/messages?recipient_id=global", headers=headers)
    assert messages_res.status_code == 200
    messages = messages_res.json()
    user_msgs = [m for m in messages if m["sender_id"] == str(user_id)]
    assert len(user_msgs) > 0
    assert user_msgs[0]["sender_name"] == "UpdatedUsername"
    assert user_msgs[0]["sender_avatar"] == "https://example.com/avatar.png"

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

@pytest.mark.asyncio
async def test_delete_account_incorrect_password_fails(async_client, authenticated_user):
    headers = authenticated_user["headers"]

    del_res = await async_client.request("DELETE", "/api/v1/users/me", json={"password": "WrongPassword123!"}, headers=headers)
    assert del_res.status_code == 400
    assert "Incorrect password" in del_res.json()["detail"]

@pytest.mark.asyncio
async def test_delete_account_auto_transfers_task_ownership(async_client):
    # Register User A (Owner)
    reg_a = await async_client.post("/api/v1/auth/register", json={
        "username": "OwnerA",
        "email": "ownera@example.com",
        "password": "Password123!"
    })
    assert reg_a.status_code == 201

    login_a = await async_client.post("/api/v1/auth/login", json={
        "email": "ownera@example.com",
        "password": "Password123!"
    })
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    # Register User B (Co-Owner: full_access)
    reg_b = await async_client.post("/api/v1/auth/register", json={
        "username": "CoOwnerB",
        "email": "coownerb@example.com",
        "password": "Password123!"
    })
    assert reg_b.status_code == 201

    login_b = await async_client.post("/api/v1/auth/login", json={
        "email": "coownerb@example.com",
        "password": "Password123!"
    })
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Register User C (Collaborator: status_only)
    reg_c = await async_client.post("/api/v1/auth/register", json={
        "username": "CollabC",
        "email": "collabc@example.com",
        "password": "Password123!"
    })
    assert reg_c.status_code == 201

    login_c = await async_client.post("/api/v1/auth/login", json={
        "email": "collabc@example.com",
        "password": "Password123!"
    })
    headers_c = {"Authorization": f"Bearer {login_c.json()['access_token']}"}

    # 1. User A creates a task
    task_res = await async_client.post("/api/v1/tasks", json={
        "title": "Shared Task Ownership Test",
        "description": "Will be transferred to User B upon User A deletion",
        "priority": 7
    }, headers=headers_a)
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # 2. Share task with User C as status_only
    req_c = await async_client.post(f"/api/v1/tasks/{task_id}/share", json={
        "target_username": "CollabC",
        "access_level": "status_only"
    }, headers=headers_a)
    assert req_c.status_code == 201
    code_c = req_c.json()["passcode"]
    id_c = req_c.json()["id"]

    res_c = await async_client.post(f"/api/v1/tasks/shares/{id_c}/respond", json={
        "passcode": code_c,
        "action": "accept"
    }, headers=headers_c)
    assert res_c.status_code == 200

    # 3. Share task with User B as full_access (Co-Owner)
    req_b = await async_client.post(f"/api/v1/tasks/{task_id}/share", json={
        "target_username": "CoOwnerB",
        "access_level": "full_access"
    }, headers=headers_a)
    assert req_b.status_code == 201
    code_b = req_b.json()["passcode"]
    id_b = req_b.json()["id"]

    res_b = await async_client.post(f"/api/v1/tasks/shares/{id_b}/respond", json={
        "passcode": code_b,
        "action": "accept"
    }, headers=headers_b)
    assert res_b.status_code == 200

    # 4. User A deletes their account with valid password
    del_res = await async_client.request("DELETE", "/api/v1/users/me", json={"password": "Password123!"}, headers=headers_a)
    assert del_res.status_code == 200
    assert del_res.json() == {"message": "Account deleted successfully"}

    # Verify User A token is now invalid
    me_a = await async_client.get("/api/v1/auth/me", headers=headers_a)
    assert me_a.status_code == 401

    # 5. User B fetches tasks -> task should now be owned by User B with my_access_level == 'owner'
    b_tasks = await async_client.get("/api/v1/tasks", headers=headers_b)
    assert b_tasks.status_code == 200
    b_items = b_tasks.json()["items"]
    transferred_task = next(t for t in b_items if t["id"] == task_id)
    assert transferred_task["owner_username"] == "CoOwnerB"
    assert transferred_task["my_access_level"] == "owner"
