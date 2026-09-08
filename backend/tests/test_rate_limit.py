"""登录/注册限流测试：纯逻辑（滑动窗口）+ 接口集成（登录爆破触发 429）。"""
import pytest

from app.core.rate_limit import SlidingWindowLimiter


def _make_limiter(max_failures: int = 3, window_seconds: float = 60.0):
    return SlidingWindowLimiter(max_failures, window_seconds)


def test_initial_not_blocked():
    limiter = _make_limiter()
    blocked, _ = limiter.is_blocked("k")
    assert blocked is False


def test_blocks_after_max_failures():
    limiter = _make_limiter(max_failures=3)
    for _ in range(3):
        limiter.record("k")
    blocked, retry_after = limiter.is_blocked("k")
    assert blocked is True
    assert retry_after >= 1


def test_below_max_not_blocked():
    limiter = _make_limiter(max_failures=3)
    for _ in range(2):
        limiter.record("k")
    blocked, _ = limiter.is_blocked("k")
    assert blocked is False


def test_reset_clears_failures():
    limiter = _make_limiter(max_failures=3)
    for _ in range(3):
        limiter.record("k")
    limiter.reset("k")
    blocked, _ = limiter.is_blocked("k")
    assert blocked is False


def test_keys_isolated():
    limiter = _make_limiter(max_failures=1)
    limiter.record("a")
    blocked, _ = limiter.is_blocked("b")
    assert blocked is False


def test_expired_failures_pruned(monkeypatch):
    limiter = _make_limiter(max_failures=2, window_seconds=10.0)
    fake_now = [1000.0]

    def fake_monotonic():
        return fake_now[0]

    monkeypatch.setattr("app.core.rate_limit.time.monotonic", fake_monotonic)
    limiter.record("k")
    fake_now[0] += 11.0  # 超出窗口
    blocked, _ = limiter.is_blocked("k")
    assert blocked is False


def test_invalid_params():
    with pytest.raises(ValueError):
        SlidingWindowLimiter(0, 60)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(5, 0)


# ---------- 接口集成：登录爆破触发 429 ----------


def _enable_aggressive_limit(monkeypatch):
    """把 auth 模块的限流器替换为小阈值实例，便于测试触发。"""
    from app.api.v1 import auth
    from app.core.rate_limit import SlidingWindowLimiter

    monkeypatch.setattr(auth, "account_limiter", SlidingWindowLimiter(2, 300))
    monkeypatch.setattr(auth, "ip_limiter", SlidingWindowLimiter(100, 300))


async def test_login_brute_force_blocked(client, monkeypatch):
    _enable_aggressive_limit(monkeypatch)
    payload = {"email": "brute@example.com", "password": "wrong"}

    resp1 = await client.post("/api/auth/login", json=payload)
    resp2 = await client.post("/api/auth/login", json=payload)
    assert resp1.status_code == 401
    assert resp2.status_code == 401

    resp3 = await client.post("/api/auth/login", json=payload)
    assert resp3.status_code == 429
    assert "Retry-After" in resp3.headers

    # 换密码不影响账号维度限流（同 IP+邮箱 仍被拦）
    resp4 = await client.post(
        "/api/auth/login", json={"email": "brute@example.com", "password": "right"}
    )
    assert resp4.status_code == 429


async def test_register_rate_limited(client, monkeypatch):
    from app.api.v1 import auth
    from app.core.rate_limit import SlidingWindowLimiter

    monkeypatch.setattr(auth, "register_limiter", SlidingWindowLimiter(2, 300))
    ok = {"full_name": "u", "password": "Passw0rd!"}
    for i in range(2):
        resp = await client.post(
            "/api/auth/register", json={**ok, "email": f"r{i}@example.com"}
        )
        assert resp.status_code == 201
    resp = await client.post(
        "/api/auth/register", json={**ok, "email": "r2@example.com"}
    )
    assert resp.status_code == 429
