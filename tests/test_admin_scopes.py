import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ArchivedSubmission, Evaluation, EvaluationTask, User, Department  # noqa: E402
from app.security import hash_password  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    parent = Department(name="上级机构", sort_order=1)
    sibling = Department(name="平级机构", sort_order=2)
    db.add_all([parent, sibling])
    db.flush()
    child = Department(name="下级机构", parent_id=parent.id, sort_order=3)
    db.add(child)
    db.flush()
    db.add_all([
        User(username="super", full_name="超级管理员", password_hash=hash_password("password!"), role="admin"),
        User(username="parent", full_name="上级管理员", password_hash=hash_password("password!"), role="admin", admin_scope_department_id=parent.id),
        User(username="child", full_name="下级管理员", password_hash=hash_password("password!"), role="admin", admin_scope_department_id=child.id),
        User(username="sibling", full_name="平级管理员", password_hash=hash_password("password!"), role="admin", admin_scope_department_id=sibling.id),
        User(username="parent-user", full_name="上级人员", password_hash=hash_password("password!"), role="user", department_id=parent.id),
        User(username="child-user", full_name="下级人员", password_hash=hash_password("password!"), role="user", department_id=child.id),
        User(username="sibling-user", full_name="平级人员", password_hash=hash_password("password!"), role="user", department_id=sibling.id),
    ])
    db.commit()
    db.close()


def login(username: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": username, "password": "password!"})
    assert response.status_code == 200
    return client


def test_department_admin_scope_filters_people_and_evaluations():
    parent = login("parent")
    child = login("child")
    sibling = login("sibling")

    parent_users = parent.get("/api/users").json()["items"]
    child_users = child.get("/api/users").json()["items"]
    assert {row["username"] for row in parent_users} == {"parent", "child", "parent-user", "child-user"}
    assert {row["username"] for row in child_users} == {"child", "child-user"}

    parent_evaluation = parent.post("/api/evaluations", json={"year": 2026, "sequence": 1, "name": "上级考核"})
    child_evaluation = child.post("/api/evaluations", json={"year": 2026, "sequence": 1, "name": "下级考核"})
    sibling_evaluation = sibling.post("/api/evaluations", json={"year": 2026, "sequence": 1, "name": "平级考核"})
    assert parent_evaluation.status_code == child_evaluation.status_code == sibling_evaluation.status_code == 201

    assert {row["name"] for row in parent.get("/api/evaluations").json()} == {"上级考核", "下级考核"}
    assert {row["name"] for row in child.get("/api/evaluations").json()} == {"下级考核"}
    assert child.get(f"/api/evaluations/{parent_evaluation.json()['id']}/config").status_code == 403


def test_public_resources_are_read_only_and_open_slot_is_scoped():
    super_admin = login("super")
    parent = login("parent")
    child = login("child")

    assert parent.get("/api/departments").status_code == 200
    assert parent.post("/api/departments", json={"name": "不可新增"}).status_code == 403

    parent_evaluation = parent.post("/api/evaluations", json={"year": 2027, "sequence": 1, "name": "上级开放考核"}).json()
    child_evaluation = child.post("/api/evaluations", json={"year": 2027, "sequence": 1, "name": "下级开放考核"}).json()
    child_second = child.post("/api/evaluations", json={"year": 2027, "sequence": 2, "name": "下级第二考核"}).json()

    assert parent.post(f"/api/evaluations/{parent_evaluation['id']}/toggle-open").status_code == 200
    assert child.post(f"/api/evaluations/{child_evaluation['id']}/toggle-open").status_code == 200
    blocked = child.post(f"/api/evaluations/{child_second['id']}/toggle-open")
    assert blocked.status_code == 409

    dashboard = parent.get("/api/dashboard/summary").json()
    assert dashboard["user_total"] == 2
    assert dashboard["department_total"] == 2
    assert dashboard["evaluation_total"] == 3

    global_evaluation = super_admin.post("/api/evaluations", json={"year": 2027, "sequence": 1, "name": "全局考核"})
    assert global_evaluation.status_code == 201
    assert all(row["name"] != "全局考核" for row in parent.get("/api/evaluations").json())


def test_review_submissions_are_limited_to_admin_department_branch():
    parent = login("parent")
    evaluation_data = parent.post(
        "/api/evaluations",
        json={"year": 2028, "sequence": 1, "name": "提交权限测试"},
    ).json()

    db = SessionLocal()
    evaluation = db.get(Evaluation, evaluation_data["id"])
    users = {item.username: item for item in db.query(User).all()}
    evaluation.tasks_generated = True
    db.add_all([
        EvaluationTask(evaluation_id=evaluation.id, reviewer_id=users[username].id, task_type="person", rule_id=index, weight=1, target_user_id=users[username].id)
        for index, username in enumerate(("parent-user", "child-user", "sibling-user"), start=1)
    ])
    db.commit()
    sibling_user_id = users["sibling-user"].id
    parent_user_id = users["parent-user"].id
    parent_department_id = users["parent-user"].department_id
    child_department_id = users["child-user"].department_id
    sibling_department_id = users["sibling-user"].department_id
    db.close()

    live = parent.get(f"/api/evaluations/{evaluation_data['id']}/review-submissions")
    assert live.status_code == 200
    assert {item["reviewer_name"] for item in live.json()["items"]} == {"上级人员", "下级人员"}
    assert parent.post(
        f"/api/evaluations/{evaluation_data['id']}/review-submissions/{parent_user_id}/details",
        json={"password": "irrelevant"},
    ).status_code == 403
    assert parent.post(
        f"/api/evaluations/{evaluation_data['id']}/review-submissions/{sibling_user_id}/details",
        json={"password": "irrelevant"},
    ).status_code == 403
    assert parent.post(
        f"/api/evaluations/{evaluation_data['id']}/review-submissions/{sibling_user_id}/reopen",
        json={},
    ).status_code == 403
    assert parent.post(
        f"/api/evaluations/{evaluation_data['id']}/review-submissions/{sibling_user_id}/cancel"
    ).status_code == 403

    db = SessionLocal()
    evaluation = db.get(Evaluation, evaluation_data["id"])
    evaluation.archived = True
    db.query(EvaluationTask).filter_by(evaluation_id=evaluation.id).delete()
    db.add_all([
        ArchivedSubmission(
            evaluation_id=evaluation.id,
            reviewer_id=index,
            reviewer_name=name,
            reviewer_department_id=department_id,
            task_count=1,
            submitted_count=1,
        )
        for index, (name, department_id) in enumerate((
            ("上级人员", parent_department_id),
            ("下级人员", child_department_id),
            ("平级人员", sibling_department_id),
        ), start=100)
    ])
    db.commit()
    db.close()

    archived = parent.get(f"/api/evaluations/{evaluation_data['id']}/review-submissions")
    assert archived.status_code == 200
    assert {item["reviewer_name"] for item in archived.json()["items"]} == {"上级人员", "下级人员"}
    assert parent.post(
        f"/api/evaluations/{evaluation_data['id']}/review-submissions/102/details",
        json={"password": "irrelevant"},
    ).status_code == 403
