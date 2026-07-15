import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Department, Evaluation, EvaluationPersonRule, Position, User  # noqa: E402
from app.security import hash_password  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="admin", full_name="管理员", password_hash=hash_password("admin123"), role="admin"))
    db.commit()
    db.close()


def admin_client() -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return client


def test_department_position_user_and_score_option_api_flow():
    client = admin_client()

    dept = client.post("/api/departments", json={"name": "办公室"}).json()
    child = client.post("/api/departments", json={"name": "监管一科", "parent_id": dept["id"], "sort_order": 1}).json()
    choices = client.get("/api/departments/choices").json()
    position = client.post("/api/positions", json={"name": "负责人"}).json()
    option = client.post("/api/score-options", json={"name": "优秀", "value": 95}).json()
    user = client.post(
        "/api/users",
        json={
            "username": "reviewer",
            "full_name": "评分人",
            "password": "123456",
            "role": "user",
            "department_id": child["id"],
            "position_id": position["id"],
        },
    ).json()

    assert child["sort_order"] == 1
    assert any(item["id"] == child["id"] and item["depth"] == 1 for item in choices)
    assert option["value"] == 95
    assert user["department_id"] == child["id"]
    assert user["must_change_password"] is True

    users = client.get("/api/users?q=评分&page=1").json()
    assert users["pagination"]["total"] == 1
    assert users["items"][0]["position_name"] == "负责人"

    users_in_parent_department = client.get(f"/api/users?department_id={dept['id']}&page=1").json()
    assert users_in_parent_department["pagination"]["total"] == 1
    assert users_in_parent_department["items"][0]["id"] == user["id"]

    reviewers = client.get(f"/api/positions/{position['id']}/reviewer-users").json()
    assert reviewers == [{"id": user["id"], "name": "评分人", "department_name": "监管一科"}]

    updated = client.put(
        f"/api/users/{user['id']}",
        json={
            "username": "reviewer",
            "full_name": "评分人A",
            "role": "user",
            "is_active": False,
            "department_id": child["id"],
            "position_id": position["id"],
            "password": "",
        },
    ).json()
    assert updated["full_name"] == "评分人A"
    assert updated["is_active"] is False
    assert client.get(f"/api/positions/{position['id']}/reviewer-users").json() == []


def test_new_user_uses_default_password_and_admin_reset_forces_password_change():
    client = admin_client()
    created = client.post(
        "/api/users",
        json={"username": "default-user", "full_name": "默认密码用户"},
    )
    assert created.status_code == 201
    user = created.json()

    login = TestClient(app).post(
        "/api/auth/login",
        json={"username": "default-user", "password": "password!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True

    reset = client.put(
        f"/api/users/{user['id']}",
        json={
            "username": "default-user",
            "full_name": "默认密码用户",
            "role": "user",
            "is_active": True,
            "password": "reset-password",
        },
    )
    assert reset.status_code == 200
    assert reset.json()["must_change_password"] is True
    assert TestClient(app).post(
        "/api/auth/login",
        json={"username": "default-user", "password": "reset-password"},
    ).status_code == 200


def test_referenced_department_and_position_delete_are_blocked():
    db = SessionLocal()
    dept = Department(name="办公室", sort_order=1)
    position = Position(name="负责人", sort_order=1)
    db.add_all([dept, position])
    db.flush()
    db.add(User(username="reviewer", full_name="评分人", password_hash=hash_password("123456"), role="user", department_id=dept.id, position_id=position.id))
    db.commit()
    department_id = dept.id
    position_id = position.id
    db.close()

    client = admin_client()
    dept_response = client.delete(f"/api/departments/{department_id}")
    position_response = client.delete(f"/api/positions/{position_id}")

    assert dept_response.status_code == 409
    assert "人员1条" in dept_response.json()["detail"]
    assert position_response.status_code == 409
    assert "人员1条" in position_response.json()["detail"]


def test_referenced_user_delete_is_blocked_with_detail():
    db = SessionLocal()
    position = Position(name="负责人", sort_order=1)
    evaluation = Evaluation(name="2026 年考核", year=2026)
    reviewer = User(username="reviewer", full_name="评分人", password_hash=hash_password("123456"), role="user")
    db.add_all([position, evaluation, reviewer])
    db.flush()
    reviewer.position_id = position.id
    db.add(EvaluationPersonRule(
        evaluation_id=evaluation.id,
        reviewer_position_id=position.id,
        reviewer_user_id=reviewer.id,
        target_position_id=position.id,
        scope_type="same_department",
        weight=1,
    ))
    db.commit()
    reviewer_id = reviewer.id
    db.close()

    response = admin_client().delete(f"/api/users/{reviewer_id}")

    assert response.status_code == 409
    assert "人员已被引用" in response.json()["detail"]
    assert "指定评价人规则1条" in response.json()["detail"]


def test_department_name_is_unique_within_its_parent_only():
    client = admin_client()
    first_parent = client.post("/api/departments", json={"name": "甲部门"}).json()
    second_parent = client.post("/api/departments", json={"name": "乙部门"}).json()

    first_child = client.post("/api/departments", json={"name": "综合科", "parent_id": first_parent["id"]})
    second_child = client.post("/api/departments", json={"name": "综合科", "parent_id": second_parent["id"]})
    duplicate_child = client.post("/api/departments", json={"name": "综合科", "parent_id": first_parent["id"]})

    assert first_child.status_code == 201
    assert second_child.status_code == 201
    assert duplicate_child.status_code == 409
    assert duplicate_child.json()["detail"] == "同一上级部门下已存在同名部门。"
