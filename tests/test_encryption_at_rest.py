import pytest
from sqlalchemy import select

from app.models.channel import ChannelModel
from app.models.task_collaborator import (
    TaskCommentModel,
    TaskHistoryModel,
)
from app.models.user import UserModel
from app.core.crypto import decrypt_field


@pytest.mark.asyncio
async def test_user_email_and_avatar_encrypted_in_db(async_client, mock_database):
    user_data = {
        "username": "crypto_user",
        "email": "crypto_user@example.com",
        "password": "Password123!"
    }
    # Register
    reg_resp = await async_client.post("/api/v1/auth/register", json=user_data)
    assert reg_resp.status_code == 201

    # Inspect raw UserModel in Database
    async with mock_database.session_factory() as session:
        stmt = select(UserModel).where(UserModel.username == "crypto_user")
        res = await session.execute(stmt)
        user_db = res.scalar_one()

        # Username MUST be stored in plain text
        assert user_db.username == "crypto_user"

        # Email MUST NOT be stored in plain text
        assert user_db.email_encrypted != "crypto_user@example.com"
        assert decrypt_field(user_db.email_encrypted) == "crypto_user@example.com"

        # email_index MUST be populated (HMAC-SHA256)
        assert user_db.email_index is not None


@pytest.mark.asyncio
async def test_channel_metadata_encrypted_in_db(async_client, authenticated_user, mock_database):
    headers = authenticated_user["headers"]
    channel_payload = {
        "name": "Secret Channel 42",
        "description": "Top secret discussions",
        "avatar_url": "https://example.com/secret_avatar.png"
    }

    # Create channel
    resp = await async_client.post("/api/v1/channels", json=channel_payload, headers=headers)
    assert resp.status_code == 201
    channel_id = resp.json()["id"]

    # Inspect DB record directly
    async with mock_database.session_factory() as session:
        stmt = select(ChannelModel).where(ChannelModel.id == channel_id)
        res = await session.execute(stmt)
        channel_db = res.scalar_one()

        # Fields MUST NOT be stored in plain text
        assert channel_db.name != "Secret Channel 42"
        assert decrypt_field(channel_db.name) == "Secret Channel 42"

        assert channel_db.description != "Top secret discussions"
        assert decrypt_field(channel_db.description) == "Top secret discussions"

        assert decrypt_field(channel_db.avatar_url) == "https://example.com/secret_avatar.png"

    # Verify API GET returns decrypted plain text
    get_resp = await async_client.get("/api/v1/channels", headers=headers)
    assert get_resp.status_code == 200
    my_channels = get_resp.json()
    assert len(my_channels) == 1
    assert my_channels[0]["name"] == "Secret Channel 42"
    assert my_channels[0]["description"] == "Top secret discussions"
    assert my_channels[0]["avatar_url"] == "https://example.com/secret_avatar.png"


@pytest.mark.asyncio
async def test_comments_and_history_encrypted_in_db(async_client, authenticated_user, mock_database):
    headers = authenticated_user["headers"]

    # 1. Create a task
    task_resp = await async_client.post("/api/v1/tasks", json={
        "title": "Encrypted Lifecycle Task",
        "description": "Testing comments & history encryption",
        "priority": 5
    }, headers=headers)
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # 2. Add a comment
    comment_resp = await async_client.post(f"/api/v1/tasks/{task_id}/comments", json={
        "content": "Confidential comment payload"
    }, headers=headers)
    assert comment_resp.status_code == 201
    comment_id = comment_resp.json()["id"]

    # Inspect raw TaskCommentModel and TaskHistoryModel in DB
    async with mock_database.session_factory() as session:
        comment_stmt = select(TaskCommentModel).where(TaskCommentModel.id == comment_id)
        comment_res = await session.execute(comment_stmt)
        comment_db = comment_res.scalar_one()

        assert comment_db.content_encrypted != "Confidential comment payload"
        assert decrypt_field(comment_db.content_encrypted) == "Confidential comment payload"

        history_stmt = select(TaskHistoryModel).where(TaskHistoryModel.task_id == task_id)
        history_res = await session.execute(history_stmt)
        history_entries = history_res.scalars().all()

        for h in history_entries:
            if h.details:
                assert decrypt_field(h.details) is not None

    # 3. Verify API GET comments & history return decrypted plain text
    comments_get = await async_client.get(f"/api/v1/tasks/{task_id}/comments", headers=headers)
    assert comments_get.status_code == 200
    assert comments_get.json()[0]["content"] == "Confidential comment payload"

    history_get = await async_client.get(f"/api/v1/tasks/{task_id}/history", headers=headers)
    assert history_get.status_code == 200
    assert len(history_get.json()) > 0
