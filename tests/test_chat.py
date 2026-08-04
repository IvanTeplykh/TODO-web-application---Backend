import pytest
from httpx import AsyncClient
from uuid import uuid4

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
