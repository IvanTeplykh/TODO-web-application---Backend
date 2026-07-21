import pytest

@pytest.mark.asyncio
async def test_create_task_success(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    task_payload = {
        "title": "Buy groceries",
        "description": "Milk, Eggs, Bread",
        "priority": 8,
        "due_date": "2026-12-31T23:59:59Z"
    }

    response = await async_client.post("/api/v1/tasks", json=task_payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "Buy groceries"
    assert data["description"] == "Milk, Eggs, Bread"
    assert data["priority"] == 8
    assert data["completed"] is False

@pytest.mark.asyncio
async def test_create_task_validation_errors(async_client, authenticated_user):
    headers = authenticated_user["headers"]

    # Title exceeds 100 characters
    long_title = "A" * 101
    res1 = await async_client.post("/api/v1/tasks", json={
        "title": long_title,
        "priority": 5
    }, headers=headers)
    assert res1.status_code == 422  # Unprocessable Entity

    # Priority out of range (>10)
    res2 = await async_client.post("/api/v1/tasks", json={
        "title": "Valid title",
        "priority": 15
    }, headers=headers)
    assert res2.status_code == 422

@pytest.mark.asyncio
async def test_get_tasks_pagination_search_filtering(async_client, authenticated_user):
    headers = authenticated_user["headers"]

    # Create multiple tasks
    await async_client.post("/api/v1/tasks", json={"title": "Task Alpha", "priority": 10}, headers=headers)
    await async_client.post("/api/v1/tasks", json={"title": "Task Beta", "priority": 5}, headers=headers)
    task3_res = await async_client.post("/api/v1/tasks", json={"title": "Task Gamma", "priority": 2}, headers=headers)
    task3_id = task3_res.json()["id"]

    # Mark Task Gamma as completed
    await async_client.patch(f"/api/v1/tasks/{task3_id}/status", json={"completed": True}, headers=headers)

    # Fetch all tasks
    all_res = await async_client.get("/api/v1/tasks", headers=headers)
    assert all_res.status_code == 200
    all_data = all_res.json()
    assert all_data["total"] == 3

    # Filter done tasks
    done_res = await async_client.get("/api/v1/tasks", params={"status": "done"}, headers=headers)
    assert done_res.status_code == 200
    done_data = done_res.json()
    assert done_data["total"] == 1
    assert done_data["items"][0]["title"] == "Task Gamma"

    # Search query
    search_res = await async_client.get("/api/v1/tasks", params={"search": "Beta"}, headers=headers)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["title"] == "Task Beta"

@pytest.mark.asyncio
async def test_update_task_details(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    create_res = await async_client.post("/api/v1/tasks", json={"title": "Original Title", "priority": 3}, headers=headers)
    task_id = create_res.json()["id"]

    update_payload = {
        "title": "Updated Title",
        "description": "New description",
        "priority": 9,
        "completed": True,
        "due_date": "2027-01-01T00:00:00Z"
    }
    update_res = await async_client.put(f"/api/v1/tasks/{task_id}", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["title"] == "Updated Title"
    assert updated_data["priority"] == 9
    assert updated_data["completed"] is True

@pytest.mark.asyncio
async def test_delete_task(async_client, authenticated_user):
    headers = authenticated_user["headers"]
    create_res = await async_client.post("/api/v1/tasks", json={"title": "To be deleted", "priority": 1}, headers=headers)
    task_id = create_res.json()["id"]

    delete_res = await async_client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert delete_res.status_code == 204

    # Fetching deleted task should return 404
    get_res = await async_client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert get_res.status_code == 404

@pytest.mark.asyncio
async def test_task_data_isolation_between_users(async_client, authenticated_user):
    user1_headers = authenticated_user["headers"]

    # Register user 2
    user2_reg = await async_client.post("/api/v1/auth/register", json={
        "username": "UserTwo",
        "email": "usertwo@example.com",
        "password": "Password123!"
    })
    assert user2_reg.status_code == 201

    user2_login = await async_client.post("/api/v1/auth/login", json={
        "email": "usertwo@example.com",
        "password": "Password123!"
    })
    user2_token = user2_login.json()["access_token"]
    user2_headers = {"Authorization": f"Bearer {user2_token}"}

    # User 1 creates task
    task_res = await async_client.post("/api/v1/tasks", json={"title": "User 1 Private Task", "priority": 5}, headers=user1_headers)
    task_id = task_res.json()["id"]

    # User 2 attempts to fetch User 1's task -> 403 Forbidden
    u2_get = await async_client.get(f"/api/v1/tasks/{task_id}", headers=user2_headers)
    assert u2_get.status_code == 403

    # User 2 attempts to delete User 1's task -> 403 Forbidden
    u2_del = await async_client.delete(f"/api/v1/tasks/{task_id}", headers=user2_headers)
    assert u2_del.status_code == 403

    # User 2 task list does not include User 1's task
    u2_list = await async_client.get("/api/v1/tasks", headers=user2_headers)
    assert u2_list.json()["total"] == 0
