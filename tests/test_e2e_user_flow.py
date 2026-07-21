import pytest

@pytest.mark.asyncio
async def test_complete_e2e_user_journey(async_client):
    user_email = "alex.dev@example.com"
    initial_password = "InitialPassword123!"
    new_password = "SuperSecretNewPassword99!"

    # -------------------------------------------------------------
    # Step 1: Pre-registration email check
    # -------------------------------------------------------------
    check_email_res = await async_client.get("/api/v1/auth/check-email", params={"email": user_email})
    assert check_email_res.status_code == 200
    assert check_email_res.json()["exists"] is False

    # -------------------------------------------------------------
    # Step 2: Register user account
    # -------------------------------------------------------------
    reg_res = await async_client.post("/api/v1/auth/register", json={
        "username": "AlexDev",
        "email": user_email,
        "password": initial_password
    })
    assert reg_res.status_code == 201
    assert reg_res.json() == {"message": "User created successfully"}

    # Verify email check post-registration
    check_email_res_2 = await async_client.get("/api/v1/auth/check-email", params={"email": user_email})
    assert check_email_res_2.json()["exists"] is True

    # -------------------------------------------------------------
    # Step 3: Login to obtain JWT Token
    # -------------------------------------------------------------
    login_res = await async_client.post("/api/v1/auth/login", json={
        "email": user_email,
        "password": initial_password
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify profile endpoint
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "AlexDev"

    # -------------------------------------------------------------
    # Step 4: Create tasks with various priorities and deadlines
    # -------------------------------------------------------------
    t1_res = await async_client.post("/api/v1/tasks", json={
        "title": "Prepare architecture proposal",
        "description": "Draft high-level system design document",
        "priority": 9,
        "due_date": "2026-12-01T12:00:00Z"
    }, headers=headers)
    assert t1_res.status_code == 201
    t1_id = t1_res.json()["id"]

    t2_res = await async_client.post("/api/v1/tasks", json={
        "title": "Review pull requests",
        "description": "Code review for team PRs",
        "priority": 7,
        "due_date": "2026-11-15T18:00:00Z"
    }, headers=headers)
    assert t2_res.status_code == 201

    t3_res = await async_client.post("/api/v1/tasks", json={
        "title": "Update API documentation",
        "description": "Refresh OpenAPI schema & README",
        "priority": 4,
        "due_date": "2026-10-30T10:00:00Z"
    }, headers=headers)
    assert t3_res.status_code == 201

    # -------------------------------------------------------------
    # Step 5: Query, Search, and Filter tasks
    # -------------------------------------------------------------
    list_all = await async_client.get("/api/v1/tasks", headers=headers)
    assert list_all.status_code == 200
    assert list_all.json()["total"] == 3

    # Search query test
    search_res = await async_client.get("/api/v1/tasks", params={"search": "architecture"}, headers=headers)
    assert search_res.json()["total"] == 1
    assert search_res.json()["items"][0]["id"] == t1_id

    # Filter undone tasks
    undone_res = await async_client.get("/api/v1/tasks", params={"status": "undone"}, headers=headers)
    assert undone_res.json()["total"] == 3

    # -------------------------------------------------------------
    # Step 6: Mark task as completed & verify status change
    # -------------------------------------------------------------
    status_patch = await async_client.patch(f"/api/v1/tasks/{t1_id}/status", json={"completed": True}, headers=headers)
    assert status_patch.status_code == 200
    assert status_patch.json()["completed"] is True

    done_res = await async_client.get("/api/v1/tasks", params={"status": "done"}, headers=headers)
    assert done_res.json()["total"] == 1
    assert done_res.json()["items"][0]["id"] == t1_id

    # -------------------------------------------------------------
    # Step 7: Update user profile and change password
    # -------------------------------------------------------------
    profile_update = await async_client.put("/api/v1/users/me", json={
        "username": "Alex Senior Dev",
        "avatar_url": "https://avatars.example.com/alex.jpg"
    }, headers=headers)
    assert profile_update.status_code == 200
    assert profile_update.json()["username"] == "Alex Senior Dev"

    # Verify old password correctness before change
    pw_val = await async_client.post("/api/v1/users/verify-password", json={"password": initial_password}, headers=headers)
    assert pw_val.json()["valid"] is True

    # Change password
    change_pw = await async_client.post("/api/v1/users/change-password", json={
        "current_password": initial_password,
        "new_password": new_password
    }, headers=headers)
    assert change_pw.status_code == 200

    # -------------------------------------------------------------
    # Step 8: Authenticate with new password & delete completed task
    # -------------------------------------------------------------
    old_pw_login = await async_client.post("/api/v1/auth/login", json={"email": user_email, "password": initial_password})
    assert old_pw_login.status_code == 401

    new_pw_login = await async_client.post("/api/v1/auth/login", json={"email": user_email, "password": new_password})
    assert new_pw_login.status_code == 200
    new_token = new_pw_login.json()["access_token"]
    new_headers = {"Authorization": f"Bearer {new_token}"}

    # Delete completed task
    delete_res = await async_client.delete(f"/api/v1/tasks/{t1_id}", headers=new_headers)
    assert delete_res.status_code == 204

    # Final task count check
    final_tasks = await async_client.get("/api/v1/tasks", headers=new_headers)
    assert final_tasks.json()["total"] == 2

    # -------------------------------------------------------------
    # Step 9: Logout
    # -------------------------------------------------------------
    logout_res = await async_client.post("/api/v1/auth/logout", headers=new_headers)
    assert logout_res.status_code == 200
