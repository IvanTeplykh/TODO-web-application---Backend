import pytest
from httpx import AsyncClient
from app.services.chat_service import chat_service
from app.schemas.chat import MessageCreate

@pytest.mark.asyncio
async def test_chat_users_list(async_client: AsyncClient, authenticated_user: dict):
    headers = authenticated_user["headers"]
    response = await async_client.get("/api/v1/chat/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)

@pytest.mark.asyncio
async def test_get_global_messages_empty(async_client: AsyncClient, authenticated_user: dict):
    headers = authenticated_user["headers"]
    response = await async_client.get("/api/v1/chat/messages?recipient_id=global", headers=headers)
    assert response.status_code == 200
    messages = response.json()
    assert isinstance(messages, list)

@pytest.mark.asyncio
async def test_chat_unauthorized(async_client: AsyncClient):
    response = await async_client.get("/api/v1/chat/users")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_chat_request_lifecycle(async_client: AsyncClient, authenticated_user: dict):
    headers1 = authenticated_user["headers"]

    # Register second user
    u2_payload = {
        "username": "UserTwo",
        "email": "user2@example.com",
        "password": "Password123!"
    }
    reg2 = await async_client.post("/api/v1/auth/register", json=u2_payload)
    assert reg2.status_code == 201

    login2 = await async_client.post("/api/v1/auth/login", json={
        "email": u2_payload["email"],
        "password": u2_payload["password"]
    })
    assert login2.status_code == 200
    t2 = login2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {t2}"}

    me2 = await async_client.get("/api/v1/auth/me", headers=headers2)
    user2_id = me2.json()["id"]

    # User 1 sends chat request to User 2
    req_res = await async_client.post("/api/v1/chat/requests", json={"recipient_id": user2_id}, headers=headers1)
    assert req_res.status_code == 201
    request_data = req_res.json()
    assert request_data["status"] == "pending"

    # User 2 lists chat requests
    list_res = await async_client.get("/api/v1/chat/requests", headers=headers2)
    assert list_res.status_code == 200
    requests_list = list_res.json()
    assert len(requests_list) >= 1

    # User 2 accepts chat request
    request_id = request_data["id"]
    accept_res = await async_client.patch(f"/api/v1/chat/requests/{request_id}", json={"action": "accept"}, headers=headers2)
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == "accepted"

@pytest.mark.asyncio
async def test_edit_and_delete_message(async_client: AsyncClient, authenticated_user: dict):
    headers = authenticated_user["headers"]
    from uuid import UUID
    user_id = UUID(authenticated_user["user"]["id"])

    # Create a message directly
    from app.core.database import db
    async with db.session_factory() as session:
        msg = await chat_service.create_message(
            session=session,
            sender_id=user_id,
            data=MessageCreate(recipient_id="global", content="Original Message")
        )
    msg_id = str(msg.id)

    # Edit message via API
    edit_res = await async_client.patch(f"/api/v1/chat/messages/{msg_id}", json={"content": "Edited Message"}, headers=headers)
    assert edit_res.status_code == 200
    edited_data = edit_res.json()
    assert edited_data["content"] == "Edited Message"
    assert edited_data["is_edited"] is True

    # Delete message via API
    del_res = await async_client.delete(f"/api/v1/chat/messages/{msg_id}", headers=headers)
    assert del_res.status_code == 200
