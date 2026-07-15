import os
from io import BytesIO

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SCORE_DETAIL_PASSWORD_HASH"] = "pbkdf2_sha256$b27c8a82fd0bdd9bc5bf8e0b2526f89c$7ddeb10e7ec017a418692e753c9dc0a0cc7af2575a0e1d7112309e81a33cddd7"

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ArchivedDepartmentScore, ArchivedPersonScore, Department, Evaluation, EvaluationDepartmentRule, EvaluationDepartmentScoreOption, EvaluationPersonRule, EvaluationScoreOption, Position, ScoreOption, User  # noqa: E402
from app.security import hash_password  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="admin", full_name="管理员", password_hash=hash_password("admin123"), role="admin"))
    db.commit()
    db.close()


def login(username: str, password: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return client


def test_api_evaluation_generation_and_user_submission_flow():
    admin = login("admin", "admin123")
    dept = admin.post("/api/departments", json={"name": "办公室"}).json()
    other_dept = admin.post("/api/departments", json={"name": "监管一科"}).json()
    director = admin.post("/api/positions", json={"name": "负责人"}).json()
    staff = admin.post("/api/positions", json={"name": "工作人员"}).json()
    excellent = admin.post("/api/score-options", json={"name": "优秀", "value": 95}).json()
    qualified = admin.post("/api/score-options", json={"name": "称职", "value": 85}).json()
    reviewer = admin.post(
        "/api/users",
        json={"username": "reviewer", "full_name": "评分人", "password": "123456", "role": "user", "department_id": dept["id"], "position_id": director["id"]},
    ).json()
    admin.post(
        "/api/users",
        json={"username": "target", "full_name": "被评人", "password": "123456", "role": "user", "department_id": dept["id"], "position_id": staff["id"]},
    )
    evaluation = admin.post("/api/evaluations", json={"year": 2026, "name": "2026 年度考核"}).json()

    db = SessionLocal()
    db.add_all([
        EvaluationScoreOption(evaluation_id=evaluation["id"], score_option_id=excellent["id"], sort_order=0),
        EvaluationScoreOption(evaluation_id=evaluation["id"], score_option_id=qualified["id"], sort_order=1),
        EvaluationDepartmentScoreOption(evaluation_id=evaluation["id"], score_option_id=excellent["id"], sort_order=0),
        EvaluationDepartmentScoreOption(evaluation_id=evaluation["id"], score_option_id=qualified["id"], sort_order=1),
        EvaluationPersonRule(evaluation_id=evaluation["id"], reviewer_position_id=director["id"], target_position_id=staff["id"], weight=0.2),
        EvaluationDepartmentRule(evaluation_id=evaluation["id"], reviewer_position_id=director["id"], target_department_id=other_dept["id"], weight=0.3),
    ])
    db.commit()
    db.close()

    generated = admin.post(f"/api/evaluations/{evaluation['id']}/generate-tasks").json()
    opened = admin.post(f"/api/evaluations/{evaluation['id']}/toggle-open").json()
    assert "已生成 2 个考核任务" in generated["message"]
    assert opened["evaluation"]["is_open"] is True

    user = login("reviewer", "123456")
    work = user.get("/api/app/evaluation").json()
    task_ids = [task["id"] for group in work["task_groups"] for task in group["tasks"]]
    assert work["evaluation"]["name"] == "2026 年度考核"
    assert work["submitted"] is False
    assert len(task_ids) == 2

    blocked = user.post("/api/app/evaluation/submit", json={"choices": {str(task_id): qualified["id"] for task_id in task_ids}})
    assert blocked.status_code == 428
    changed = user.post("/api/auth/change-password", json={"current_password": "123456", "new_password": "reviewer-new-password"})
    assert changed.status_code == 200
    submit = user.post("/api/app/evaluation/submit", json={"choices": {str(task_id): qualified["id"] for task_id in task_ids}})
    assert submit.status_code == 200
    assert submit.json()["message"] == "评分已提交。"

    after_submit = user.get("/api/app/evaluation").json()
    assert after_submit["submitted"] is True
    assert after_submit["current_choices"][str(task_ids[0])] == qualified["id"]
    assert reviewer["username"] == "reviewer"

    denied = admin.post(
        f"/api/evaluations/{evaluation['id']}/review-submissions/{reviewer['id']}/details",
        json={"password": "wrong"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "查看密码错误。"

    details = admin.post(
        f"/api/evaluations/{evaluation['id']}/review-submissions/{reviewer['id']}/details",
        json={"password": "Bijie@2026!"},
    )
    assert details.status_code == 200
    detail_data = details.json()
    assert detail_data["reviewer"]["full_name"] == "评分人"
    assert detail_data["pagination"]["total"] == 2
    assert {item["target_name"] for item in detail_data["items"]} == {"被评人", "监管一科"}
    assert all(item["option_name"] == "称职" for item in detail_data["items"])
    assert all(item["weighted_score"] > 0 for item in detail_data["items"])

    duplicate = user.post(
        "/api/app/evaluation/submit",
        json={"choices": {str(task_id): excellent["id"] for task_id in task_ids}},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "你已经提交过本次考核，请勿重复提交。"

    missing_confirmation = admin.post(f"/api/evaluations/{evaluation['id']}/clear-tasks")
    assert missing_confirmation.status_code == 409

    cleared = admin.post(f"/api/evaluations/{evaluation['id']}/clear-tasks?confirm=true")
    assert cleared.status_code == 200
    assert cleared.json()["evaluation"]["total_tasks"] == 0
    assert cleared.json()["evaluation"]["tasks_generated"] is False
    assert cleared.json()["evaluation"]["is_open"] is False


def test_same_year_batches_copy_and_single_open_evaluation():
    admin = login("admin", "admin123")

    first_response = admin.post("/api/evaluations", json={"year": 2026, "name": ""})
    second_response = admin.post("/api/evaluations", json={"year": 2026, "name": ""})

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first = first_response.json()
    second = second_response.json()
    assert (first["sequence"], first["name"]) == (1, "2026-01")
    assert (second["sequence"], second["name"]) == (2, "2026-02")

    duplicate = admin.post(
        "/api/evaluations",
        json={"year": 2026, "sequence": 2, "name": "重复批次"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "2026 年第 2 批考核已存在。"

    copied_response = admin.post(
        f"/api/evaluations/{first['id']}/copy",
        json={"year": 2026, "name": ""},
    )
    assert copied_response.status_code == 200
    copied = copied_response.json()["evaluation"]
    assert (copied["sequence"], copied["name"]) == (3, "2026-03")

    opened = admin.post(f"/api/evaluations/{first['id']}/toggle-open")
    blocked = admin.post(f"/api/evaluations/{second['id']}/toggle-open")
    assert opened.status_code == 200
    assert opened.json()["evaluation"]["is_open"] is True
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "“2026-01”正在开放，请先关闭该考核。"


def test_person_rule_scope_is_normalized_and_validated():
    admin = login("admin", "admin123")
    department = admin.post("/api/departments", json={"name": "办公室"}).json()
    reviewer_position = admin.post("/api/positions", json={"name": "负责人"}).json()
    target_position = admin.post("/api/positions", json={"name": "工作人员"}).json()
    evaluation = admin.post("/api/evaluations", json={"year": 2026, "name": "范围测试"}).json()
    base_payload = {
        "reviewer_position_id": reviewer_position["id"],
        "target_position_id": target_position["id"],
        "weight": 1,
    }

    missing_departments = admin.post(
        f"/api/evaluations/{evaluation['id']}/person-rules",
        json={**base_payload, "scope_type": "selected_departments", "target_department_ids": []},
    )
    assert missing_departments.status_code == 422
    assert missing_departments.json()["detail"] == "请选择被评部门范围。"

    created = admin.post(
        f"/api/evaluations/{evaluation['id']}/person-rules",
        json={**base_payload, "scope_type": "same_department", "target_department_ids": [department["id"]]},
    )
    assert created.status_code == 200
    config = admin.get(f"/api/evaluations/{evaluation['id']}/config").json()
    assert config["person_rules"][0]["scope_type"] == "same_department"
    assert config["person_rules"][0]["target_department_ids"] == []


def test_archived_scores_can_be_exported_as_excel():
    db = SessionLocal()
    evaluation = Evaluation(name="2026 年考核", year=2026, archived=True)
    db.add(evaluation)
    db.flush()
    db.add_all([
        ArchivedPersonScore(evaluation_id=evaluation.id, user_id=1, username="u1", full_name="张三", department_name="办公室", position_name="干部", final_score=91.5),
        ArchivedDepartmentScore(evaluation_id=evaluation.id, department_id=1, department_name="办公室", final_score=88.0),
    ])
    db.commit()
    evaluation_id = evaluation.id
    db.close()

    admin = login("admin", "admin123")
    people_response = admin.get(f"/api/evaluations/{evaluation_id}/exports/person-scores")
    department_response = admin.get(f"/api/evaluations/{evaluation_id}/exports/department-scores")

    assert people_response.status_code == 200
    people_sheet = load_workbook(BytesIO(people_response.content)).active
    assert list(people_sheet.values) == [("姓名", "所在部门", "得分"), ("张三", "办公室", 91.5)]
    department_sheet = load_workbook(BytesIO(department_response.content)).active
    assert list(department_sheet.values) == [("部门名称", "得分"), ("办公室", 88)]
