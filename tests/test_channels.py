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

    # 5. Add User 2 to Channel (send invitation)
    add_m_res = await async_client.post(f"/api/v1/channels/{channel_id}/members", json={"user_id": user2_id}, headers=headers1)
    assert add_m_res.status_code == 201
    assert add_m_res.json()["role"] == "member"
    assert add_m_res.json()["status"] == "pending"

    # 5.5 User 2 accepts channel invitation
    inv_res = await async_client.get("/api/v1/channels/invites/pending", headers=headers2)
    assert inv_res.status_code == 200
    invites = inv_res.json()
    assert len(invites) >= 1
    invite_id = invites[0]["id"]

    acc_res = await async_client.post(f"/api/v1/channels/invites/{invite_id}/respond?action=accept", headers=headers2)
    assert acc_res.status_code == 200

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


@pytest.mark.asyncio
async def test_channel_manual_username_invite_and_decline(async_client: AsyncClient, authenticated_user: dict):
    headers1 = authenticated_user["headers"]

    # 1. Create target user to be invited by username
    u3_payload = {
        "username": "UserByManualName",
        "email": "user3_manual@example.com",
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

    # 2. Create Channel as User 1
    create_res = await async_client.post("/api/v1/channels", json={"name": "Manual Invite Test Channel"}, headers=headers1)
    assert create_res.status_code == 201
    channel_id = create_res.json()["id"]

    # 3. Invite user manually by username (case-insensitive test)
    invite_res = await async_client.post(
        f"/api/v1/channels/{channel_id}/members",
        json={"username": "userbymanualname"},
        headers=headers1
    )
    assert invite_res.status_code == 201
    inv_data = invite_res.json()
    assert inv_data["username"] == "UserByManualName"
    assert inv_data["status"] == "pending"

    # 4. Check channel members list (Owner perspective) - pending member must show status="pending"
    members_res = await async_client.get(f"/api/v1/channels/{channel_id}/members", headers=headers1)
    assert members_res.status_code == 200
    members = members_res.json()
    pending_m = next(m for m in members if m["username"] == "UserByManualName")
    assert pending_m["status"] == "pending"

    # 5. User 3 checks pending invites and declines
    pending_res = await async_client.get("/api/v1/channels/invites/pending", headers=headers3)
    assert pending_res.status_code == 200
    invites = pending_res.json()
    assert len(invites) == 1
    invite_id = invites[0]["id"]

    dec_res = await async_client.post(f"/api/v1/channels/invites/{invite_id}/respond?action=decline", headers=headers3)
    assert dec_res.status_code == 200
    assert dec_res.json()["status"] == "declined"

    # 6. Verify non-existent username returns 404
    err_res = await async_client.post(
        f"/api/v1/channels/{channel_id}/members",
        json={"username": "non_existent_user_12345"},
        headers=headers1
    )
    assert err_res.status_code == 404

