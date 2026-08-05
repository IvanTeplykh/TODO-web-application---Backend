import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_task_sharing_full_flow(async_client: AsyncClient, authenticated_user: dict):
    headers1 = authenticated_user["headers"]

    # 1. Register and login User 2
    u2_payload = {
        "username": "TaskShareMemberTwo",
        "email": "taskmember2@example.com",
        "password": "Password123!"
    }
    reg2 = await async_client.post("/api/v1/auth/register", json=u2_payload)
    assert reg2.status_code == 201

    login2 = await async_client.post("/api/v1/auth/login", json={
        "email": u2_payload["email"],
        "password": u2_payload["password"]
    })
    assert login2.status_code == 200
    headers2 = {"Authorization": f"Bearer {login2.json()['access_token']}"}

    # 2. Create Task as User 1
    create_task_res = await async_client.post(
        "/api/v1/tasks",
        json={
            "title": "Collaborative Design Review",
            "priority": 8,
            "description": "Review sprint mockups with team"
        },
        headers=headers1
    )
    assert create_task_res.status_code == 201
    task1 = create_task_res.json()
    task1_id = task1["id"]
    assert task1["my_access_level"] == "owner"

    # 3. Share task with User 2 as 'status_only'
    share_req_res = await async_client.post(
        f"/api/v1/tasks/{task1_id}/share",
        json={
            "target_username": "TaskShareMemberTwo",
            "access_level": "status_only"
        },
        headers=headers1
    )
    assert share_req_res.status_code == 201
    share_data = share_req_res.json()
    req_id = share_data["id"]
    passcode = share_data["passcode"]
    assert len(passcode) == 6

    # 4. User 2 checks pending task shares
    pending_shares_res = await async_client.get("/api/v1/tasks/shares/pending", headers=headers2)
    assert pending_shares_res.status_code == 200
    pending_shares = pending_shares_res.json()
    assert len(pending_shares) == 1
    assert pending_shares[0]["id"] == req_id

    # 5. User 2 fails to accept with wrong passcode
    wrong_acc_res = await async_client.post(
        f"/api/v1/tasks/shares/{req_id}/respond",
        json={"passcode": "000000", "action": "accept"},
        headers=headers2
    )
    assert wrong_acc_res.status_code == 400

    # 6. User 2 accepts with correct passcode
    acc_res = await async_client.post(
        f"/api/v1/tasks/shares/{req_id}/respond",
        json={"passcode": passcode, "action": "accept"},
        headers=headers2
    )
    assert acc_res.status_code == 200

    # 7. User 2 fetches task list - task should now be listed with 'status_only' access level
    user2_tasks_res = await async_client.get("/api/v1/tasks", headers=headers2)
    assert user2_tasks_res.status_code == 200
    u2_items = user2_tasks_res.json()["items"]
    assert len(u2_items) == 1
    assert u2_items[0]["id"] == task1_id
    assert u2_items[0]["my_access_level"] == "status_only"

    # 8. User 2 (status_only) CAN update status
    st_update_res = await async_client.patch(
        f"/api/v1/tasks/{task1_id}/status",
        json={"completed": True},
        headers=headers2
    )
    assert st_update_res.status_code == 200
    assert st_update_res.json()["completed"] is True

    # 9. User 2 (status_only) CANNOT update title/description (403)
    edit_err_res = await async_client.put(
        f"/api/v1/tasks/{task1_id}",
        json={
            "title": "Hacked Title",
            "priority": 1,
            "completed": True,
            "description": "Attempted edit"
        },
        headers=headers2
    )
    assert edit_err_res.status_code == 403

    # 10. User 2 (status_only) CANNOT delete task (403)
    del_err_res = await async_client.delete(f"/api/v1/tasks/{task1_id}", headers=headers2)
    assert del_err_res.status_code == 403

    # 11. Check Task History (Audit Log)
    history_res = await async_client.get(f"/api/v1/tasks/{task1_id}/history", headers=headers1)
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 3 # created, share_requested, status_changed
    actions = [h["action"] for h in history]
    assert "created" in actions
    assert "status_changed" in actions

@pytest.mark.asyncio
async def test_task_transfer_ownership_flow(async_client: AsyncClient, authenticated_user: dict):
    headers1 = authenticated_user["headers"]

    # 1. Register User 3
    u3_payload = {
        "username": "TaskTransferMemberThree",
        "email": "taskmember3@example.com",
        "password": "Password123!"
    }
    reg3 = await async_client.post("/api/v1/auth/register", json=u3_payload)
    assert reg3.status_code == 201

    login3 = await async_client.post("/api/v1/auth/login", json={
        "email": u3_payload["email"],
        "password": u3_payload["password"]
    })
    assert login3.status_code == 200
    headers3 = {"Authorization": f"Bearer {login3.json()['access_token']}"}

    # 2. Create Task as User 1
    create_task_res = await async_client.post(
        "/api/v1/tasks",
        json={"title": "Ownership Transfer Test Task", "priority": 5},
        headers=headers1
    )
    assert create_task_res.status_code == 201
    task_id = create_task_res.json()["id"]

    # 3. Create Transfer request to User 3
    share_res = await async_client.post(
        f"/api/v1/tasks/{task_id}/share",
        json={"target_username": "TaskTransferMemberThree", "access_level": "transfer"},
        headers=headers1
    )
    assert share_res.status_code == 201
    req_id = share_res.json()["id"]
    passcode = share_res.json()["passcode"]

    # 4. User 3 accepts transfer with passcode
    acc_res = await async_client.post(
        f"/api/v1/tasks/shares/{req_id}/respond",
        json={"passcode": passcode, "action": "accept"},
        headers=headers3
    )
    assert acc_res.status_code == 200

    # 5. Verify User 3 is now the owner
    get_task_res = await async_client.get(f"/api/v1/tasks/{task_id}", headers=headers3)
    assert get_task_res.status_code == 200
    assert get_task_res.json()["my_access_level"] == "owner"

    # 5b. Verify User 1 (old owner) is now a full_access collaborator
    get_task_old_owner = await async_client.get(f"/api/v1/tasks/{task_id}", headers=headers1)
    assert get_task_old_owner.status_code == 200
    assert get_task_old_owner.json()["my_access_level"] == "full_access"

    # 6. User 3 can delete task
    del_res = await async_client.delete(f"/api/v1/tasks/{task_id}", headers=headers3)
    assert del_res.status_code == 204

@pytest.mark.asyncio
async def test_task_comments_flow(async_client: AsyncClient, authenticated_user: dict):
    headers1 = authenticated_user["headers"]

    # 1. Register User 4
    u4_payload = {
        "username": "TaskCommentMemberFour",
        "email": "taskmember4@example.com",
        "password": "Password123!"
    }
    reg4 = await async_client.post("/api/v1/auth/register", json=u4_payload)
    assert reg4.status_code == 201
    login4 = await async_client.post("/api/v1/auth/login", json={
        "email": u4_payload["email"],
        "password": u4_payload["password"]
    })
    headers4 = {"Authorization": f"Bearer {login4.json()['access_token']}"}

    # 2. Create Task as User 1
    create_res = await async_client.post(
        "/api/v1/tasks",
        json={"title": "Task with Comments", "priority": 5},
        headers=headers1
    )
    task_id = create_res.json()["id"]

    # 3. Share task with User 4
    share_res = await async_client.post(
        f"/api/v1/tasks/{task_id}/share",
        json={"target_username": "TaskCommentMemberFour", "access_level": "status_only"},
        headers=headers1
    )
    req_id = share_res.json()["id"]
    passcode = share_res.json()["passcode"]

    # User 4 accepts
    await async_client.post(
        f"/api/v1/tasks/shares/{req_id}/respond",
        json={"passcode": passcode, "action": "accept"},
        headers=headers4
    )

    # 4. Owner (User 1) posts a comment
    c1_res = await async_client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "Welcome to the task discussion!"},
        headers=headers1
    )
    assert c1_res.status_code == 201
    c1 = c1_res.json()
    assert c1["author_name"] == authenticated_user["user"]["username"]

    # 5. Member (User 4) posts a comment
    c2_res = await async_client.post(
        f"/api/v1/tasks/{task_id}/comments",
        json={"content": "Thanks! I'll update status as soon as I test it."},
        headers=headers4
    )
    assert c2_res.status_code == 201
    c2 = c2_res.json()
    assert c2["author_name"] == "TaskCommentMemberFour"

    # 6. Fetch comments
    list_comments = await async_client.get(f"/api/v1/tasks/{task_id}/comments", headers=headers4)
    assert list_comments.status_code == 200
    comments = list_comments.json()
    assert len(comments) == 2

    # 7. Member updates their own comment
    up_res = await async_client.put(
        f"/api/v1/tasks/{task_id}/comments/{c2['id']}",
        json={"content": "Updated comment text!"},
        headers=headers4
    )
    assert up_res.status_code == 200
    assert up_res.json()["content"] == "Updated comment text!"

    # 8. Owner deletes member's comment (owner moderation)
    del_res = await async_client.delete(f"/api/v1/tasks/{task_id}/comments/{c2['id']}", headers=headers1)
    assert del_res.status_code == 204
