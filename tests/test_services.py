import os
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Department,
    Evaluation,
    ArchivedRuleSnapshot,
    ArchivedSubmission,
    EvaluationDepartmentManualScore,
    EvaluationDepartmentRule,
    EvaluationDepartmentRuleOptionLimit,
    EvaluationDepartmentScoreOption,
    EvaluationDepartmentScoreShareRule,
    EvaluationPersonPositionOptionLimit,
    EvaluationPersonRuleOptionLimit,
    EvaluationPersonRule,
    EvaluationPersonRuleDepartment,
    EvaluationReviewReopen,
    EvaluationScoreOption,
    EvaluationTask,
    EvaluationVote,
    Position,
    ScoreOption,
    User,
)
from app.security import hash_password, verify_password  # noqa: E402
from app.services import archive_evaluation, calculate_evaluation_scores, generate_tasks, submit_votes, validate_vote_payload  # noqa: E402
from app.api.evaluations import copy_evaluation, copy_evaluation_preview  # noqa: E402


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_case():
    db = SessionLocal()
    dept = Department(name="办公室")
    other_dept = Department(name="监管一科")
    director = Position(name="负责人")
    staff = Position(name="工作人员")
    db.add_all([dept, other_dept, director, staff])
    db.flush()
    admin = User(username="admin", full_name="管理员", password_hash=hash_password("secret"), role="admin")
    reviewer = User(username="r1", full_name="评分人", password_hash=hash_password("123456"), role="user", department_id=dept.id, position_id=director.id)
    target = User(username="t1", full_name="被评人", password_hash=hash_password("123456"), role="user", department_id=dept.id, position_id=staff.id)
    peer = User(username="r2", full_name="同职位", password_hash=hash_password("123456"), role="user", department_id=dept.id, position_id=director.id)
    excellent = ScoreOption(name="优秀", value=95)
    qualified = ScoreOption(name="称职", value=85)
    evaluation = Evaluation(year=2026)
    db.add_all([admin, reviewer, target, peer, excellent, qualified, evaluation])
    db.flush()
    person_rule = EvaluationPersonRule(evaluation_id=evaluation.id, reviewer_position_id=director.id, target_position_id=staff.id, weight=0.2)
    department_rule = EvaluationDepartmentRule(evaluation_id=evaluation.id, reviewer_position_id=director.id, target_department_id=other_dept.id, weight=0.3)
    db.add_all([person_rule, department_rule])
    db.flush()
    db.add_all([
        EvaluationScoreOption(evaluation_id=evaluation.id, score_option_id=excellent.id, sort_order=0),
        EvaluationScoreOption(evaluation_id=evaluation.id, score_option_id=qualified.id, sort_order=1),
        EvaluationDepartmentScoreOption(evaluation_id=evaluation.id, score_option_id=excellent.id, sort_order=0),
        EvaluationDepartmentScoreOption(evaluation_id=evaluation.id, score_option_id=qualified.id, sort_order=1),
        EvaluationPersonPositionOptionLimit(evaluation_id=evaluation.id, target_position_id=staff.id, score_option_id=excellent.id, max_people=1),
        EvaluationPersonPositionOptionLimit(evaluation_id=evaluation.id, target_position_id=staff.id, score_option_id=qualified.id, max_people=None),
        EvaluationDepartmentRuleOptionLimit(rule_id=department_rule.id, score_option_id=excellent.id, max_people=None),
        EvaluationDepartmentRuleOptionLimit(rule_id=department_rule.id, score_option_id=qualified.id, max_people=None),
    ])
    db.commit()
    return db, evaluation.id, reviewer.id, target.id, other_dept.id


def submit_all_reviewers(db, evaluation, option):
    task_model = __import__("app.models").models.EvaluationTask
    reviewer_ids = {
        task.reviewer_id
        for task in db.query(task_model).filter_by(evaluation_id=evaluation.id).all()
    }
    for reviewer_id in reviewer_ids:
        reviewer = db.get(User, reviewer_id)
        tasks = db.query(task_model).filter_by(evaluation_id=evaluation.id, reviewer_id=reviewer_id).all()
        submit_votes(db, evaluation, reviewer, {task.id: option.id for task in tasks})


def test_password_hash_round_trip():
    stored = hash_password("secret")
    assert verify_password("secret", stored)
    assert not verify_password("wrong", stored)


def test_generate_tasks_excludes_self_and_uses_selected_department_only():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    count = generate_tasks(db, evaluation)
    tasks = db.query(__import__("app.models").models.EvaluationTask).all()
    assert count == 4
    assert all(task.target_user_id != task.reviewer_id for task in tasks if task.task_type == "person")
    assert {task.target_department_id for task in tasks if task.task_type == "department"} == {other_dept_id}
    db.close()


def test_person_rule_filters_targets_by_multiple_departments():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    staff = db.query(Position).filter_by(name="工作人员").one()
    other_dept = db.get(Department, other_dept_id)
    included = User(username="t2", full_name="被评人2", password_hash=hash_password("123456"), role="user", department_id=other_dept.id, position_id=staff.id)
    excluded_dept = Department(name="不参与部门")
    db.add_all([included, excluded_dept])
    db.flush()
    excluded = User(username="t3", full_name="不参与人员", password_hash=hash_password("123456"), role="user", department_id=excluded_dept.id, position_id=staff.id)
    db.add(excluded)
    rule = db.query(EvaluationPersonRule).filter_by(evaluation_id=evaluation_id).one()
    db.add_all([
        EvaluationPersonRuleDepartment(rule_id=rule.id, department_id=other_dept.id),
    ])
    db.commit()

    evaluation = db.get(Evaluation, evaluation_id)
    generate_tasks(db, evaluation)
    person_tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(task_type="person").all()
    assert {task.target_user_id for task in person_tasks} == {included.id}
    db.close()


def test_person_rule_same_department_scope_uses_reviewer_department():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    staff = db.query(Position).filter_by(name="工作人员").one()
    other_dept = db.get(Department, other_dept_id)
    other_dept_staff = User(username="t2", full_name="外部门人员", password_hash=hash_password("123456"), role="user", department_id=other_dept.id, position_id=staff.id)
    db.add(other_dept_staff)
    rule = db.query(EvaluationPersonRule).filter_by(evaluation_id=evaluation_id).one()
    rule.scope_type = "same_department"
    db.commit()

    evaluation = db.get(Evaluation, evaluation_id)
    generate_tasks(db, evaluation)
    person_tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(task_type="person").all()
    assert {task.target_user_id for task in person_tasks} == {target_id}
    db.close()


def test_person_rule_can_target_one_specified_reviewer():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    rule = db.query(EvaluationPersonRule).filter_by(evaluation_id=evaluation_id).one()
    rule.reviewer_user_id = reviewer_id
    db.commit()

    evaluation = db.get(Evaluation, evaluation_id)
    generate_tasks(db, evaluation)
    person_tasks = db.query(EvaluationTask).filter_by(task_type="person").all()

    assert {task.reviewer_id for task in person_tasks} == {reviewer_id}
    assert {task.target_user_id for task in person_tasks} == {target_id}
    db.close()


def test_submit_votes_enforces_option_quota_per_reviewer_person_task():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    generate_tasks(db, evaluation)
    reviewer = db.get(User, reviewer_id)
    tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer_id).all()
    excellent = db.query(ScoreOption).filter_by(name="优秀").one()
    choices = {task.id: excellent.id for task in tasks}
    assert validate_vote_payload(db, evaluation, reviewer, choices) == []
    submit_votes(db, evaluation, reviewer, choices)
    assert validate_vote_payload(db, evaluation, reviewer, choices) == ["你已经提交过本次考核，不能重复提交。"]
    db.close()


def test_person_option_quota_is_shared_by_target_position_across_rules():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    staff = db.query(Position).filter_by(name="工作人员").one()
    director = db.query(Position).filter_by(name="负责人").one()
    dept = db.query(Department).filter_by(name="办公室").one()
    target_two = User(username="t2", full_name="被评人2", password_hash=hash_password("123456"), role="user", department_id=dept.id, position_id=staff.id)
    second_rule = EvaluationPersonRule(evaluation_id=evaluation_id, reviewer_position_id=director.id, target_position_id=staff.id, weight=0.1)
    db.add_all([target_two, second_rule])
    db.commit()

    evaluation.is_open = True
    generate_tasks(db, evaluation)
    reviewer = db.get(User, reviewer_id)
    excellent = db.query(ScoreOption).filter_by(name="优秀").one()
    tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer_id).all()
    choices = {task.id: excellent.id for task in tasks}
    errors = validate_vote_payload(db, evaluation, reviewer, choices)

    assert errors == ["“优秀”对“工作人员”最多选择 1 人。"]
    db.close()


def test_archive_keeps_snapshot_after_org_changes():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    generate_tasks(db, evaluation)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    submit_all_reviewers(db, evaluation, qualified)
    archive_evaluation(db, evaluation)
    person_score = db.query(__import__("app.models").models.ArchivedPersonScore).one()
    assert db.query(ArchivedRuleSnapshot).filter_by(evaluation_id=evaluation_id).count() > 0
    assert db.query(ArchivedSubmission).filter_by(evaluation_id=evaluation_id).count() > 0
    assert db.query(EvaluationTask).filter_by(evaluation_id=evaluation_id).count() == 0
    assert db.query(EvaluationVote).filter_by(evaluation_id=evaluation_id).count() == 0
    assert db.query(EvaluationPersonRule).filter_by(evaluation_id=evaluation_id).count() == 0
    target = db.get(User, target_id)
    db.delete(target)
    db.commit()
    assert db.get(User, target_id) is None
    assert person_score.full_name == "被评人"
    assert isinstance(person_score.final_score, Decimal)
    assert person_score.final_score == Decimal("17.0000")
    db.close()


def test_archived_evaluation_can_copy_configuration_from_snapshot():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    generate_tasks(db, evaluation)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    submit_all_reviewers(db, evaluation, qualified)
    archive_evaluation(db, evaluation)
    admin = db.query(User).filter_by(role="admin").one()

    old_option_id = qualified.id
    db.delete(qualified)
    db.flush()
    preview = copy_evaluation_preview(evaluation_id, db, admin)
    assert {item["source_id"] for item in preview["missing"]} == {old_option_id}

    result = copy_evaluation(evaluation_id, {
        "year": 2027,
        "name": "2027 年考核",
    }, db, admin)
    copied = result["evaluation"]

    assert copied.archived is False
    assert db.query(EvaluationPersonRule).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationDepartmentRule).filter_by(evaluation_id=copied.id).count() == 1
    assert db.query(EvaluationScoreOption).filter_by(evaluation_id=copied.id).count() == 1
    assert result["skipped_count"] == 3
    assert result["message"] == f"考核已复制，共复制 {result['copied_count']}条配置，跳过 3条失效配置。"
    db.close()


def test_archived_copy_skips_person_rule_when_specified_reviewer_is_missing():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    person_rule = db.query(EvaluationPersonRule).filter_by(evaluation_id=evaluation_id).one()
    person_rule.reviewer_user_id = reviewer_id
    db.commit()

    generate_tasks(db, evaluation)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    submit_all_reviewers(db, evaluation, qualified)
    archive_evaluation(db, evaluation)
    admin = db.query(User).filter_by(role="admin").one()
    db.delete(db.get(User, reviewer_id))
    db.commit()

    result = copy_evaluation(evaluation_id, {"year": 2027, "name": "2027 年考核"}, db, admin)
    copied_id = result["evaluation"].id

    assert db.query(EvaluationPersonRule).filter_by(evaluation_id=copied_id).count() == 0
    assert db.query(EvaluationDepartmentRule).filter_by(evaluation_id=copied_id).count() == 1
    assert result["skipped_count"] == 1
    assert "指定评价人已删除" in result["skipped"][0]
    db.close()


def test_archive_requires_all_tasks_completed():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    generate_tasks(db, evaluation)
    reviewer = db.get(User, reviewer_id)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer_id).all()
    submit_votes(db, evaluation, reviewer, {task.id: qualified.id for task in tasks})

    try:
        archive_evaluation(db, evaluation)
    except ValueError as exc:
        assert "所有考核任务完成后才能归档" in str(exc)
    else:
        raise AssertionError("未完成全部任务时不应允许归档")
    db.close()


def test_archive_applies_manual_department_share_rule_to_people():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    staff = db.query(Position).filter_by(name="工作人员").one()
    dept = db.query(Department).filter_by(name="办公室").one()
    db.add_all([
        EvaluationDepartmentScoreShareRule(
            evaluation_id=evaluation_id,
            target_position_id=staff.id,
            weight=0.1,
        ),
        EvaluationDepartmentManualScore(evaluation_id=evaluation_id, department_id=dept.id, score=90),
    ])
    db.commit()

    evaluation.is_open = True
    generate_tasks(db, evaluation)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    submit_all_reviewers(db, evaluation, qualified)
    archive_evaluation(db, evaluation)

    person_score = db.query(__import__("app.models").models.ArchivedPersonScore).filter_by(user_id=target_id).one()
    manual_department_score = db.query(__import__("app.models").models.ArchivedDepartmentScore).filter_by(department_id=dept.id).one()
    assert person_score.final_score == 26.0
    assert manual_department_score.final_score == 90
    db.close()


def test_live_scores_use_same_calculation_as_archive():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    staff = db.query(Position).filter_by(name="工作人员").one()
    dept = db.query(Department).filter_by(name="办公室").one()
    db.add_all([
        EvaluationDepartmentScoreShareRule(
            evaluation_id=evaluation_id,
            target_position_id=staff.id,
            weight=0.1,
        ),
        EvaluationDepartmentManualScore(evaluation_id=evaluation_id, department_id=dept.id, score=90),
    ])
    db.commit()

    evaluation.is_open = True
    generate_tasks(db, evaluation)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    submit_all_reviewers(db, evaluation, qualified)

    live = calculate_evaluation_scores(db, evaluation)
    live_person = next(item for item in live["people"] if item["user_id"] == target_id)
    live_department = next(item for item in live["departments"] if item["department_id"] == dept.id)
    assert live["submitted_tasks"] == live["total_tasks"]
    assert live_person["final_score"] == 26.0
    assert live_department["final_score"] == 90

    archive_evaluation(db, evaluation)
    archived_person = db.query(__import__("app.models").models.ArchivedPersonScore).filter_by(user_id=target_id).one()
    archived_department = db.query(__import__("app.models").models.ArchivedDepartmentScore).filter_by(department_id=dept.id).one()
    assert archived_person.final_score == live_person["final_score"]
    assert archived_department.final_score == live_department["final_score"]
    db.close()


def test_scores_average_votes_within_same_rule_before_applying_weight():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    generate_tasks(db, evaluation)

    reviewer = db.get(User, reviewer_id)
    peer = db.query(User).filter_by(username="r2").one()
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    excellent = db.query(ScoreOption).filter_by(name="优秀").one()

    reviewer_tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(
        evaluation_id=evaluation_id,
        reviewer_id=reviewer.id,
    ).all()
    peer_tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(
        evaluation_id=evaluation_id,
        reviewer_id=peer.id,
    ).all()
    submit_votes(db, evaluation, reviewer, {task.id: qualified.id for task in reviewer_tasks})
    submit_votes(db, evaluation, peer, {task.id: excellent.id for task in peer_tasks})

    live = calculate_evaluation_scores(db, evaluation)
    live_person = next(item for item in live["people"] if item["user_id"] == target_id)
    live_department = next(item for item in live["departments"] if item["department_id"] == other_dept_id)

    assert live_person["final_score"] == 18.0
    assert live_department["final_score"] == 27.0
    db.close()


def test_person_score_group_averages_split_rules_before_weighting():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    director = db.query(Position).filter_by(name="负责人").one()
    staff = db.query(Position).filter_by(name="工作人员").one()
    peer = db.query(User).filter_by(username="r2").one()
    first_rule = db.query(EvaluationPersonRule).filter_by(evaluation_id=evaluation_id).one()
    first_rule.reviewer_user_id = reviewer_id
    first_rule.score_group = "负责人评价工作人员"
    second_rule = EvaluationPersonRule(
        evaluation_id=evaluation_id,
        reviewer_position_id=director.id,
        reviewer_user_id=peer.id,
        target_position_id=staff.id,
        score_group="负责人评价工作人员",
        weight=0.2,
    )
    db.add(second_rule)
    db.commit()

    evaluation.is_open = True
    generate_tasks(db, evaluation)
    reviewer = db.get(User, reviewer_id)
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    excellent = db.query(ScoreOption).filter_by(name="优秀").one()
    reviewer_tasks = db.query(EvaluationTask).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer.id).all()
    peer_tasks = db.query(EvaluationTask).filter_by(evaluation_id=evaluation_id, reviewer_id=peer.id).all()
    submit_votes(db, evaluation, reviewer, {task.id: qualified.id for task in reviewer_tasks})
    submit_votes(db, evaluation, peer, {task.id: excellent.id for task in peer_tasks})

    live = calculate_evaluation_scores(db, evaluation)
    live_person = next(item for item in live["people"] if item["user_id"] == target_id)

    assert live_person["final_score"] == 18.0
    db.close()


def test_reopened_review_can_replace_previous_votes_once():
    db, evaluation_id, reviewer_id, target_id, other_dept_id = seed_case()
    evaluation = db.get(Evaluation, evaluation_id)
    evaluation.is_open = True
    generate_tasks(db, evaluation)
    reviewer = db.get(User, reviewer_id)
    admin = db.query(User).filter_by(username="admin").one()
    qualified = db.query(ScoreOption).filter_by(name="称职").one()
    excellent = db.query(ScoreOption).filter_by(name="优秀").one()
    tasks = db.query(__import__("app.models").models.EvaluationTask).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer_id).all()
    submit_votes(db, evaluation, reviewer, {task.id: qualified.id for task in tasks})

    errors = validate_vote_payload(db, evaluation, reviewer, {task.id: excellent.id for task in tasks})
    assert errors == ["你已经提交过本次考核，不能重复提交。"]

    db.add(EvaluationReviewReopen(evaluation_id=evaluation_id, reviewer_id=reviewer_id, created_by=admin.id))
    db.commit()
    submit_votes(db, evaluation, reviewer, {task.id: excellent.id for task in tasks})

    votes = db.query(EvaluationVote).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer_id).all()
    assert len(votes) == len(tasks)
    assert {vote.score_option_id for vote in votes} == {excellent.id}
    assert db.query(EvaluationReviewReopen).filter_by(evaluation_id=evaluation_id, reviewer_id=reviewer_id).count() == 0
    db.close()
