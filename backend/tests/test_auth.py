"""M1 认证模块测试。

覆盖注册 / 登录 / 身份 / 权限 / 无效 JWT / 角色管理等验收标准。
"""
from tests.conftest import TEST_DB_URL

REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "password": "Passw0rd!",
    "full_name": "Alice",
}

ADMIN_PAYLOAD = {
    "email": "admin@example.com",
    "password": "Admin@123",
    "full_name": "Admin",
}


async def _register(client, payload: dict):
    return await client.post("/api/auth/register", json=payload)


async def _login(client, email: str, password: str):
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


# ---------- 注册 ----------

async def test_register_success(client):
    resp = await _register(client, REGISTER_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["email"] == "alice@example.com"
    assert data["role"] == "operator"
    assert "password" not in resp.text


async def test_register_duplicate_email(client):
    await _register(client, REGISTER_PAYLOAD)
    resp = await _register(client, REGISTER_PAYLOAD)
    assert resp.status_code == 409


async def test_register_weak_password(client):
    resp = await _register(client, {**REGISTER_PAYLOAD, "password": "short"})
    assert resp.status_code == 422


async def test_register_invalid_email(client):
    resp = await _register(client, {"email": "not-an-email", "password": "Passw0rd!"})
    assert resp.status_code == 422


# ---------- 登录 ----------

async def test_login_success(client):
    await _register(client, REGISTER_PAYLOAD)
    resp = await _login(client, "alice@example.com", "Passw0rd!")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["expires_in"] > 0


async def test_login_wrong_password(client):
    await _register(client, REGISTER_PAYLOAD)
    resp = await _login(client, "alice@example.com", "wrong-password")
    assert resp.status_code == 401


async def test_login_unknown_email(client):
    resp = await _login(client, "ghost@example.com", "Passw0rd!")
    assert resp.status_code == 401


# ---------- /me ----------

async def test_me_with_token(client):
    await _register(client, REGISTER_PAYLOAD)
    login = await _login(client, "alice@example.com", "Passw0rd!")
    token = login.json()["data"]["access_token"]
    resp = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "alice@example.com"


async def test_me_without_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_invalid_token(client):
    resp = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.valid.token"}
    )
    assert resp.status_code == 401


async def test_me_update_full_name(client):
    await _register(client, REGISTER_PAYLOAD)
    login = await _login(client, "alice@example.com", "Passw0rd!")
    token = login.json()["data"]["access_token"]
    resp = await client.put(
        "/api/auth/me",
        json={"full_name": "Bobby"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Bobby"


# ---------- refresh ----------

async def test_refresh_token(client):
    await _register(client, REGISTER_PAYLOAD)
    login = await _login(client, "alice@example.com", "Passw0rd!")
    refresh_token = login.json()["data"]["refresh_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


async def test_refresh_with_access_token_fails(client):
    await _register(client, REGISTER_PAYLOAD)
    login = await _login(client, "alice@example.com", "Passw0rd!")
    access_token = login.json()["data"]["access_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


# ---------- 用户管理（admin） ----------

async def _make_admin(client):
    resp = await _register(client, ADMIN_PAYLOAD)
    user_id = resp.json()["data"]["id"]
    # 直接改库把第一个用户提升为 admin
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.user import User

    engine = create_async_engine(TEST_DB_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        user = await session.get(User, user_id)
        user.role = "admin"
        await session.commit()
    await engine.dispose()


async def test_require_admin_rejects_operator(client):
    await _register(client, REGISTER_PAYLOAD)
    login = await _login(client, "alice@example.com", "Passw0rd!")
    token = login.json()["data"]["access_token"]
    resp = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


async def test_admin_lists_users(client):
    await _register(client, REGISTER_PAYLOAD)
    await _make_admin(client)
    login = await _login(client, "admin@example.com", "Admin@123")
    token = login.json()["data"]["access_token"]
    resp = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] >= 1


async def test_admin_update_role(client):
    created = await _register(client, REGISTER_PAYLOAD)
    target_id = created.json()["data"]["id"]
    await _make_admin(client)
    login = await _login(client, "admin@example.com", "Admin@123")
    token = login.json()["data"]["access_token"]
    resp = await client.patch(
        f"/api/v1/users/{target_id}/role",
        json={"role": "analyst"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "analyst"


async def test_admin_update_role_invalid(client):
    created = await _register(client, REGISTER_PAYLOAD)
    target_id = created.json()["data"]["id"]
    await _make_admin(client)
    login = await _login(client, "admin@example.com", "Admin@123")
    token = login.json()["data"]["access_token"]
    resp = await client.patch(
        f"/api/v1/users/{target_id}/role",
        json={"role": "superadmin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
