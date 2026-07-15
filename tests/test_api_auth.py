import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserSession  # noqa: E402
from app.security import hash_password, session_token_hash  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add_all([
        User(
            username="admin",
            full_name="管理员",
            password_hash=hash_password("admin123"),
            role="admin",
        ),
        User(
            username="reviewer",
            full_name="评分人",
            password_hash=hash_password("123456"),
            role="user",
        ),
    ])
    db.commit()
    db.close()


def test_api_me_requires_login():
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录。"


def test_api_login_rejects_invalid_password():
    client = TestClient(app)

    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "bad"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误。"


def test_api_login_sets_cookie_and_returns_current_user():
    client = TestClient(app)

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    me = client.get("/api/auth/me")

    assert login.status_code == 200
    assert login.json()["redirect_to"] == "/admin"
    assert login.json()["user"]["role"] == "admin"
    assert "personnel_session" in login.cookies
    assert login.cookies.get("user_id") in (None, "")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    token = login.cookies["personnel_session"]
    with SessionLocal() as db:
        session = db.query(UserSession).one()
        assert session.token_hash == session_token_hash(token)
        assert token != session.token_hash


def test_forged_legacy_user_id_cookie_cannot_authenticate():
    client = TestClient(app)
    client.cookies.set("user_id", "1")

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_api_admin_dependency_rejects_normal_user():
    client = TestClient(app)
    client.post(
        "/api/auth/login",
        json={"username": "reviewer", "password": "123456"},
    )

    response = client.get("/api/users")

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限。"


def test_system_name_is_public_and_only_admin_can_update_it():
    public = TestClient(app)
    initial = public.get("/api/settings")
    assert initial.status_code == 200
    assert initial.json()["system_name"]

    public.post("/api/auth/login", json={"username": "reviewer", "password": "123456"})
    denied = public.put("/api/settings", json={"system_name": "新系统"})
    assert denied.status_code == 403

    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    updated = admin.put("/api/settings", json={"system_name": "新系统名称"})
    assert updated.status_code == 200
    assert admin.get("/api/settings").json()["system_name"] == "新系统名称"


def test_api_logout_clears_cookie():
    client = TestClient(app)
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )

    logout = client.post("/api/auth/logout")
    me = client.get("/api/auth/me")

    assert logout.status_code == 200
    assert logout.json()["message"] == "已退出登录。"
    assert me.status_code == 401


def test_user_can_change_own_password():
    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "reviewer", "password": "123456"})
    other_session = TestClient(app)
    other_session.post("/api/auth/login", json={"username": "reviewer", "password": "123456"})

    wrong = client.post("/api/auth/change-password", json={"current_password": "bad", "new_password": "newpass"})
    changed = client.post("/api/auth/change-password", json={"current_password": "123456", "new_password": "newpass"})
    old_login = TestClient(app).post("/api/auth/login", json={"username": "reviewer", "password": "123456"})
    new_login = TestClient(app).post("/api/auth/login", json={"username": "reviewer", "password": "newpass"})

    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "当前密码不正确。"
    assert changed.status_code == 200
    assert changed.json()["message"] == "密码修改成功。"
    assert client.get("/api/auth/me").status_code == 200
    assert other_session.get("/api/auth/me").status_code == 401
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_forced_password_change_blocks_writes_until_password_is_changed():
    with SessionLocal() as db:
        reviewer = db.query(User).filter_by(username="reviewer").one()
        reviewer.must_change_password = True
        db.commit()

    client = TestClient(app)
    login_response = client.post("/api/auth/login", json={"username": "reviewer", "password": "123456"})

    assert login_response.json()["user"]["must_change_password"] is True
    blocked = client.put("/api/settings", json={"system_name": "不能修改"})
    assert blocked.status_code == 428
    assert blocked.json()["detail"] == "首次登录或密码已被重置，请先修改密码。"

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": "123456", "new_password": "changed-password"},
    )
    assert changed.status_code == 200
    assert client.get("/api/auth/me").json()["must_change_password"] is False


def test_health_and_request_id_are_observable():
    client = TestClient(app)

    live = client.get("/health/live", headers={"X-Request-ID": "test-request-123"})
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.headers["X-Request-ID"] == "test-request-123"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok"}


def test_spa_routes_return_frontend_entrypoint_after_refresh():
    client = TestClient(app)

    for path in ("/admin", "/admin/evaluations", "/app/evaluation"):
        response = client.get(path)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert '<div id="root"></div>' in response.text
