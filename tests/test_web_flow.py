import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Department, Evaluation, EvaluationDepartmentManualScore, EvaluationDepartmentOptionLimit, EvaluationDepartmentRule, EvaluationDepartmentScoreOption, EvaluationDepartmentScoreShareRule, EvaluationPersonPositionOptionLimit, EvaluationPersonRule, EvaluationPersonRuleDepartment, EvaluationScoreOption, EvaluationTask, EvaluationVote, Position, ScoreOption, User  # noqa: E402
from app.security import hash_password  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(username="admin", full_name="管理员", password_hash=hash_password("admin123"), role="admin"))
    db.commit()
    db.close()


def test_admin_to_user_archive_flow():
    admin_client = TestClient(app)
    admin = admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    assert admin.status_code == 200

    admin_client.post("/admin/departments", data={"name": "办公室", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/departments", data={"name": "监管一科", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/positions", data={"name": "负责人"})
    admin_client.post("/admin/positions", data={"name": "工作人员"})
    admin_client.post("/admin/score-options", data={"name": "优秀", "value": "95"})
    admin_client.post("/admin/score-options", data={"name": "称职", "value": "85"})
    admin_client.post("/admin/users", data={"username": "reviewer", "full_name": "评分人", "password": "123456", "role": "user", "department_id": "1", "position_id": "1"})
    admin_client.post("/admin/users", data={"username": "target", "full_name": "被评人", "password": "123456", "role": "user", "department_id": "1", "position_id": "2"})
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "2026 年度考核"})
    admin_client.post(
        "/admin/evaluations/1/settings/person-options",
        data={"option_ids": ["1", "2"]},
    )
    admin_client.post(
        "/admin/evaluations/1/settings/person-limits",
        data={"target_position_id": "2", "score_option_id": "1", "max_people": "1"},
    )
    admin_client.post("/admin/evaluations/1/settings/department-options", data={"option_ids": ["1", "2"]})
    admin_client.post("/admin/evaluations/1/settings/department-limits", data={"score_option_id": "1", "max_count": "1"})
    admin_client.post("/admin/evaluations/1/settings/person-rules", data={"reviewer_position_id": "1", "target_position_id": "2", "score_option_ids": ["1", "2"], "weight": "0.2"})
    admin_client.post("/admin/evaluations/1/settings/department-rules", data={"reviewer_position_id": "1", "target_department_id": "2", "score_option_ids": ["1", "2"], "weight": "0.3"})
    admin_client.post("/admin/evaluations/1/generate-tasks")
    admin_client.post("/admin/evaluations/1/toggle-open")

    user_client = TestClient(app)
    user = user_client.post("/login", data={"username": "reviewer", "password": "123456"}, follow_redirects=True)
    assert "2026 年度考核评分" in user.text
    assert "被评对象：工作人员" in user.text
    assert "优秀最多 1 人" in user.text
    assert "一键选择" in user.text
    assert "覆盖已选" not in user.text
    assert 'data-quick-fill-option="1"' in user.text
    assert "人员评分：" not in user.text
    assert "部门考核" in user.text
    assert "优秀最多 1 个" in user.text
    assert "部门评分：" not in user.text
    assert "权重" not in user.text
    assert "优秀（95" not in user.text
    assert user.text.index("被评对象：工作人员") < user.text.index("部门考核")
    db = SessionLocal()
    task_ids = [task.id for task in db.query(EvaluationTask).order_by(EvaluationTask.id).all()]
    reviewer_id = db.query(User).filter_by(username="reviewer").one().id
    db.close()
    user_client.post("/app/evaluation/submit", data={f"task_{task_id}": "2" for task_id in task_ids})

    db = SessionLocal()
    assert db.query(EvaluationVote).count() == 2
    db.close()

    submissions = admin_client.get("/admin/evaluations/1/review-submissions")
    assert submissions.status_code == 200
    assert "评分提交管理" in submissions.text
    assert "每页 10 人" in submissions.text
    assert "允许修改" in submissions.text
    reopen_response = admin_client.post(
        f"/admin/evaluations/1/review-submissions/{reviewer_id}/reopen",
        data={"page": "2", "q": "评分人"},
        follow_redirects=False,
    )
    assert reopen_response.headers["location"] == "/admin/evaluations/1/review-submissions?page=2&q=%E8%AF%84%E5%88%86%E4%BA%BA"
    reopen = admin_client.get(reopen_response.headers["location"])
    assert "已退回可修改" in reopen.text
    reopened_page = user_client.get("/app/evaluation")
    assert "重新修改本次评分" in reopened_page.text
    assert "checked" in reopened_page.text
    user_client.post("/app/evaluation/submit", data={f"task_{task_id}": "2" for task_id in task_ids})
    after_reopen = admin_client.get("/admin/evaluations/1/review-submissions")
    assert "已退回可修改" not in after_reopen.text

    live = admin_client.get("/admin/evaluations/1/live-stats")
    assert live.status_code == 200
    assert "实时进度" in live.text
    assert "人员当前得分" in live.text
    assert "部门当前得分" in live.text
    assert "被评人" in live.text
    assert "每页 10 条" in live.text
    assert "每页 20 条" in live.text

    detail = admin_client.post("/admin/evaluations/1/archive", data={"confirm_action": "yes"}, follow_redirects=True)
    assert "人员得分" in detail.text
    assert "被评人" in detail.text
    assert "评分明细快照" in detail.text
    assert "归档规则快照" in detail.text
    assert "每页 10 条" in detail.text
    assert "每页 20 条" in detail.text
    evaluations = admin_client.get("/admin/evaluations")
    assert "操作审计" in evaluations.text
    audit = admin_client.get("/admin/evaluations/audit")
    assert audit.status_code == 200
    assert "审计记录" in audit.text
    assert "归档考核" in audit.text
    assert "2024 年以来" in audit.text


def test_admin_updates_person_rule_departments():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/departments", data={"name": "办公室", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/departments", data={"name": "监管一科", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/departments", data={"name": "监管二科", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/positions", data={"name": "负责人"})
    admin_client.post("/admin/positions", data={"name": "工作人员"})
    admin_client.post("/admin/score-options", data={"name": "优秀", "value": "95"})
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "2026 年度考核"})
    admin_client.post(
        "/admin/evaluations/1/settings/person-rules",
        data={
            "reviewer_position_id": "1",
            "target_position_id": "2",
            "target_department_ids": ["1"],
            "scope_type": "selected_departments",
            "score_option_ids": ["1"],
            "weight": "0.2",
        },
    )

    response = admin_client.post(
        "/admin/evaluations/1/settings/person-rules/1/update",
        data={
            "reviewer_position_id": "1",
            "target_position_id": "2",
            "scope_type": "same_department",
            "target_department_ids": ["2", "3"],
            "score_option_ids": ["1"],
            "weight": "0.5",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    db = SessionLocal()
    rule = db.get(EvaluationPersonRule, 1)
    department_ids = {
        item.department_id
        for item in db.query(EvaluationPersonRuleDepartment).filter_by(rule_id=1).all()
    }
    assert rule.weight == 0.5
    assert rule.scope_type == "same_department"
    assert department_ids == {2, 3}
    db.close()


def test_admin_copies_evaluation_settings_only():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/departments", data={"name": "办公室", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/positions", data={"name": "负责人"})
    admin_client.post("/admin/positions", data={"name": "工作人员"})
    admin_client.post("/admin/score-options", data={"name": "优秀", "value": "95"})
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "源考核"})
    admin_client.post(
        "/admin/evaluations/1/settings/person-options",
        data={"option_ids": ["1"]},
    )
    admin_client.post(
        "/admin/evaluations/1/settings/person-limits",
        data={"target_position_id": "2", "score_option_id": "1", "max_people": "1"},
    )
    admin_client.post("/admin/evaluations/1/settings/department-options", data={"option_ids": ["1"]})
    admin_client.post("/admin/evaluations/1/settings/department-limits", data={"score_option_id": "1", "max_count": "1"})
    admin_client.post(
        "/admin/evaluations/1/settings/department-share-rules",
        data={"target_position_id": "2", "weight": "0.1"},
    )
    admin_client.post(
        "/admin/evaluations/1/settings/manual-department-scores",
        data={"department_id": "1", "score": "90"},
    )
    admin_client.post(
        "/admin/evaluations/1/settings/person-rules",
        data={
            "reviewer_position_id": "1",
            "target_position_id": "2",
            "scope_type": "selected_departments",
            "target_department_ids": ["1"],
            "score_option_ids": ["1"],
            "max_people_limits": ["1"],
            "weight": "0.2",
        },
    )
    admin_client.post("/admin/evaluations/1/settings/department-rules", data={"reviewer_position_id": "1", "target_department_id": "1", "score_option_ids": ["1"], "max_people_limits": ["1"], "weight": "0.3"})
    admin_client.post("/admin/evaluations/1/copy", data={"year": "2027", "name": "复制考核"})

    db = SessionLocal()
    copied = db.query(Evaluation).filter_by(year=2027).one()
    assert copied.name == "复制考核"
    assert db.query(EvaluationScoreOption).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationDepartmentScoreOption).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationPersonRule).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationDepartmentRule).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationPersonPositionOptionLimit).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationDepartmentOptionLimit).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationDepartmentScoreShareRule).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationDepartmentManualScore).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationTask).filter_by(evaluation_id=copied.id).count() == 0
    db.close()


def test_dashboard_search_filters_evaluations():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "年度考核"})
    admin_client.post("/admin/evaluations", data={"year": "2027", "name": "专项考核"})

    response = admin_client.get("/admin?q=专项")

    assert response.status_code == 200
    assert "专项考核" in response.text
    assert "年度考核" not in response.text
    assert "筛选⌄" not in response.text
    assert "更多⌄" not in response.text


def test_referenced_base_items_cannot_be_deleted():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/departments", data={"name": "办公室", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/positions", data={"name": "负责人"})
    admin_client.post("/admin/score-options", data={"name": "优秀", "value": "95"})
    admin_client.post("/admin/users", data={"username": "reviewer", "full_name": "评分人", "password": "123456", "role": "user", "department_id": "1", "position_id": "1"})
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "2026 年度考核"})
    admin_client.post("/admin/evaluations/1/settings/person-options", data={"option_ids": ["1"]})

    department_response = admin_client.post("/admin/departments/1/delete", follow_redirects=True)
    position_response = admin_client.post("/admin/positions/1/delete", follow_redirects=True)
    option_response = admin_client.post("/admin/score-options/1/delete", follow_redirects=True)

    assert "已被引用，不能删除" in department_response.text
    assert "已被引用，不能删除" in position_response.text
    assert "已被引用，不能删除" in option_response.text
    db = SessionLocal()
    assert db.query(Department).count() == 1
    assert db.query(Position).count() == 1
    assert db.query(ScoreOption).count() == 1
    db.close()


def test_archived_evaluation_is_disabled_and_delete_requires_admin_password():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    db = SessionLocal()
    db.add(Evaluation(year=2026, name="已归档考核", archived=True))
    db.commit()
    db.close()

    page = admin_client.get("/admin/evaluations")
    assert 'aria-disabled="true">人员考核规则' in page.text
    assert "disabled>任务生成" in page.text
    assert "当前管理员密码" in page.text

    blocked = admin_client.get("/admin/evaluations/1/person-rules", follow_redirects=True)
    assert "已归档考核只能查看详情、复制或删除" in blocked.text

    bad_delete = admin_client.post("/admin/evaluations/1/delete", data={"admin_password": "wrong"}, follow_redirects=True)
    assert "删除已归档考核前请输入当前管理员密码" in bad_delete.text
    db = SessionLocal()
    assert db.query(Evaluation).count() == 1
    db.close()

    good_delete = admin_client.post("/admin/evaluations/1/delete", data={"admin_password": "admin123"}, follow_redirects=True)
    assert "考核已删除" in good_delete.text
    db = SessionLocal()
    assert db.query(Evaluation).count() == 0
    db.close()


def test_generated_evaluation_shows_regenerate_task_action():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    db = SessionLocal()
    db.add(Evaluation(year=2026, name="已生成考核", tasks_generated=True))
    db.commit()
    db.close()

    page = admin_client.get("/admin/evaluations")

    assert "重新生成任务" in page.text
    assert page.text.index("人员考核规则") < page.text.index("部门考核规则") < page.text.index("部门得分占比")
    assert page.text.index("部门得分占比") < page.text.index("重新生成任务") < page.text.index("开始考核")
    assert page.text.index("归档统计") < page.text.index("详情") < page.text.index("复制") < page.text.index("删除")


def test_department_rules_support_multiple_hierarchical_departments():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/departments", data={"name": "总部门", "parent_id": "", "score_note": "", "sort_order": "1"})
    admin_client.post("/admin/departments", data={"name": "子部门", "parent_id": "1", "score_note": "", "sort_order": "1"})
    admin_client.post("/admin/departments", data={"name": "并列部门", "parent_id": "", "score_note": "", "sort_order": "2"})
    admin_client.post("/admin/positions", data={"name": "负责人"})
    admin_client.post("/admin/score-options", data={"name": "优秀", "value": "95"})
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "2026 年度考核"})
    admin_client.post("/admin/evaluations/1/settings/department-options", data={"option_ids": ["1"]})

    response = admin_client.post(
        "/admin/evaluations/1/settings/department-rules",
        data={
            "reviewer_position_id": "1",
            "target_department_ids": ["1", "2"],
            "score_option_ids": ["1"],
            "max_people_limits": ["1"],
            "weight": "0.3",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "全选部门" not in response.text
    assert "总部门" in response.text
    assert "子部门" in response.text
    assert 'data-parent-id="1"' in response.text
    assert "data-tree-toggle" in response.text
    assert "data-tree-toggle-label" in response.text
    assert "data-select-descendants" in response.text
    db = SessionLocal()
    rules = db.query(EvaluationDepartmentRule).order_by(EvaluationDepartmentRule.target_department_id).all()
    assert [rule.target_department_id for rule in rules] == [1, 2]
    db.close()


def test_department_limit_entry_is_visible_and_requires_department_options():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/score-options", data={"name": "部门优秀", "value": "95"})
    admin_client.post("/admin/evaluations", data={"year": "2026", "name": "2026 年度考核"})

    page = admin_client.get("/admin/evaluations/1/department-rules")
    assert "新增评分限制" in page.text
    assert "请先在“部门评分选项”中勾选并保存可用评分项" in page.text
    assert "请先勾选并保存部门评分选项" in page.text

    blocked = admin_client.post(
        "/admin/evaluations/1/settings/department-limits",
        data={"score_option_id": "1", "max_count": "1"},
        follow_redirects=True,
    )
    assert "请先保存该部门评分选项后再设置数量限制" in blocked.text

    admin_client.post("/admin/evaluations/1/settings/department-options", data={"option_ids": ["1"]})
    saved = admin_client.post(
        "/admin/evaluations/1/settings/department-limits",
        data={"score_option_id": "1", "max_count": "1"},
        follow_redirects=True,
    )
    assert "部门评分限制已保存" in saved.text
    db = SessionLocal()
    assert db.query(EvaluationDepartmentOptionLimit).count() == 1
    db.close()


def test_admin_sorting_and_user_pagination():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    admin_client.post("/admin/departments", data={"name": "后排部门", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/departments", data={"name": "前排部门", "parent_id": "", "score_note": ""})
    admin_client.post("/admin/positions", data={"name": "后排职位"})
    admin_client.post("/admin/positions", data={"name": "前排职位"})
    admin_client.post("/admin/departments/1/update", data={"name": "后排部门", "parent_id": "", "score_note": "", "sort_order": "2"})
    admin_client.post("/admin/departments/2/update", data={"name": "前排部门", "parent_id": "", "score_note": "", "sort_order": "1"})
    admin_client.post("/admin/positions/1/update", data={"name": "后排职位", "sort_order": "2"})
    admin_client.post("/admin/positions/2/update", data={"name": "前排职位", "sort_order": "1"})

    admin_client.post("/admin/users", data={"username": "late", "full_name": "后排人员", "password": "123456", "role": "user", "department_id": "1", "position_id": "1"})
    admin_client.post("/admin/users", data={"username": "middle", "full_name": "中间人员", "password": "123456", "role": "user", "department_id": "2", "position_id": "1"})
    admin_client.post("/admin/users", data={"username": "early", "full_name": "前排人员", "password": "123456", "role": "user", "department_id": "2", "position_id": "2"})
    for index in range(22):
        admin_client.post(
            "/admin/users",
            data={
                "username": f"bulk{index}",
                "full_name": f"批量人员{index}",
                "password": "123456",
                "role": "user",
                "department_id": "1",
                "position_id": "1",
            },
        )

    db = SessionLocal()
    assert [item.name for item in db.query(Department).order_by(Department.sort_order, Department.id).all()] == ["前排部门", "后排部门"]
    assert [item.name for item in db.query(Position).order_by(Position.sort_order, Position.id).all()] == ["前排职位", "后排职位"]
    db.close()

    departments_response = admin_client.post(
        "/admin/departments/1/update",
        data={"name": "后排部门", "parent_id": "", "score_note": "", "sort_order": "12"},
        follow_redirects=True,
    )
    assert 'value="2"' in departments_response.text

    positions_response = admin_client.post(
        "/admin/positions/1/update",
        data={"name": "后排职位", "sort_order": "11"},
        follow_redirects=True,
    )
    assert 'value="2"' in positions_response.text

    response = admin_client.get("/admin/users")
    assert "第 1 / 3 页" in response.text
    assert "每页 10 人" in response.text
    early_index = response.text.index("前排人员")
    middle_index = response.text.index("中间人员")
    late_index = response.text.index("后排人员")
    assert early_index < middle_index < late_index


def test_department_and_position_sort_order_update_inserts_before_target_position():
    admin_client = TestClient(app)
    admin_client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    for name in ["部门一", "部门二", "部门三", "部门四", "部门五"]:
        admin_client.post("/admin/departments", data={"name": name, "parent_id": "", "score_note": ""})
    for name in ["职位一", "职位二", "职位三", "职位四", "职位五"]:
        admin_client.post("/admin/positions", data={"name": name})

    admin_client.post(
        "/admin/departments/5/update",
        data={"name": "部门五", "parent_id": "", "score_note": "", "sort_order": "3"},
    )
    admin_client.post("/admin/positions/2/update", data={"name": "职位二", "sort_order": "99"})

    db = SessionLocal()
    departments = db.query(Department).order_by(Department.sort_order, Department.id).all()
    positions = db.query(Position).order_by(Position.sort_order, Position.id).all()
    assert [(item.name, item.sort_order) for item in departments] == [
        ("部门一", 1),
        ("部门二", 2),
        ("部门五", 3),
        ("部门三", 4),
        ("部门四", 5),
    ]
    assert [(item.name, item.sort_order) for item in positions] == [
        ("职位一", 1),
        ("职位三", 2),
        ("职位四", 3),
        ("职位五", 4),
        ("职位二", 5),
    ]
    db.close()
