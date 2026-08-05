import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_channel_full_lifecycle(async_client: AsyncClient, authenticated_user: dict):
    headers1 = authenticated_user["headers"]

    # 1. Create second user
    u2_payload = {
        "username": "ChannelMemberTwo",
        "email": "channel2@example.com",
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

    me2 = await async_client.get("/api/v1/auth/me", headers=headers2)
    user2_id = me2.json()["id"]

    # 2. Create Channel as User 1
    ch_payload = {
        "name": "Dev Team Channel",
        "description": "General channel for development",
        "avatar_url": "https://example.com/ch-avatar.png"
    }
    create_res = await async_client.post("/api/v1/channels", json=ch_payload, headers=headers1)
    assert create_res.status_code == 201
    ch_data = create_res.json()
    channel_id = ch_data["id"]
    assert ch_data["name"] == "Dev Team Channel"
    assert ch_data["my_role"] == "owner"

    # 3. List my channels
    list_res = await async_client.get("/api/v1/channels", headers=headers1)
    assert list_res.status_code == 200
    my_channels = list_res.json()
    assert len(my_channels) >= 1

    # 4. Update channel info (User 1 = Owner)
    update_res = await async_client.patch(f"/api/v1/channels/{channel_id}", json={
        "name": "Updated Dev Channel",
        "avatar_url": "https://example.com/new-avatar.png"
    }, headers=headers1)
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Updated Dev Channel"
    assert update_res.json()["avatar_url"] == "https://example.com/new-avatar.png"

    # 5. Add User 2 to Channel
    add_m_res = await async_client.post(f"/api/v1/channels/{channel_id}/members", json={"user_id": user2_id}, headers=headers1)
    assert add_m_res.status_code == 201
    assert add_m_res.json()["role"] == "member"

    # 6. Promote User 2 to Admin
    role_res = await async_client.patch(f"/api/v1/channels/{channel_id}/members/{user2_id}/role", json={"role": "admin"}, headers=headers1)
    assert role_res.status_code == 200
    assert role_res.json()["role"] == "admin"

    # 7. User 1 posts a message
    msg1_res = await async_client.post(f"/api/v1/channels/{channel_id}/messages", json={"content": "Hello channel from Owner!"}, headers=headers1)
    assert msg1_res.status_code == 201
    msg1_id = msg1_res.json()["id"]

    # 8. User 2 (Admin) deletes User 1's message (Admin deletion capability)
    del_msg_res = await async_client.delete(f"/api/v1/channels/{channel_id}/messages/{msg1_id}", headers=headers2)
    assert del_msg_res.status_code == 200

    # 9. User 2 posts a message
    msg2_res = await async_client.post(f"/api/v1/channels/{channel_id}/messages", json={"content": "Hello from Admin!"}, headers=headers2)
    assert msg2_res.status_code == 201

    # 10. List channel messages
    get_msgs_res = await async_client.get(f"/api/v1/channels/{channel_id}/messages", headers=headers1)
    assert get_msgs_res.status_code == 200
    msgs = get_msgs_res.json()
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello from Admin!"

    # 11. Delete Channel (Owner)
    del_ch_res = await async_client.delete(f"/api/v1/channels/{channel_id}", headers=headers1)
    assert del_ch_res.status_code == 200
