import json
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    ArchivedDepartmentScore,
    ArchivedPersonScore,
    ArchivedRuleSnapshot,
    ArchivedVoteDetail,
    Department,
    Evaluation,
    EvaluationDepartmentOptionLimit,
    EvaluationDepartmentManualScore,
    EvaluationDepartmentRule,
    EvaluationDepartmentRuleOptionLimit,
    EvaluationDepartmentScoreOption,
    EvaluationDepartmentScoreShareRule,
    EvaluationPersonRule,
    EvaluationPersonPositionOptionLimit,
    EvaluationPersonRuleOptionLimit,
    EvaluationScoreOption,
    EvaluationReviewReopen,
    EvaluationTask,
    EvaluationVote,
    Position,
    ScoreOption,
    User,
)


def evaluation_person_options(db: Session, evaluation_id: int) -> list[ScoreOption]:
    stmt = (
        select(ScoreOption)
        .join(EvaluationScoreOption, EvaluationScoreOption.score_option_id == ScoreOption.id)
        .where(EvaluationScoreOption.evaluation_id == evaluation_id)
        .order_by(EvaluationScoreOption.sort_order, EvaluationScoreOption.id)
    )
    return list(db.scalars(stmt))


def evaluation_department_options(db: Session, evaluation_id: int) -> list[ScoreOption]:
    stmt = (
        select(ScoreOption)
        .join(EvaluationDepartmentScoreOption, EvaluationDepartmentScoreOption.score_option_id == ScoreOption.id)
        .where(EvaluationDepartmentScoreOption.evaluation_id == evaluation_id)
        .order_by(EvaluationDepartmentScoreOption.sort_order, EvaluationDepartmentScoreOption.id)
    )
    return list(db.scalars(stmt))


def generate_tasks(db: Session, evaluation: Evaluation) -> int:
    db.execute(delete(EvaluationVote).where(EvaluationVote.evaluation_id == evaluation.id))
    db.execute(delete(EvaluationReviewReopen).where(EvaluationReviewReopen.evaluation_id == evaluation.id))
    db.execute(delete(EvaluationTask).where(EvaluationTask.evaluation_id == evaluation.id))
    created = 0

    person_rules = db.scalars(
        select(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == evaluation.id)
    ).all()
    for rule in person_rules:
        reviewer_stmt = select(User).where(
            User.role == "user",
            User.is_active.is_(True),
            User.position_id == rule.reviewer_position_id,
        )
        if rule.reviewer_user_id:
            reviewer_stmt = reviewer_stmt.where(User.id == rule.reviewer_user_id)
        reviewers = db.scalars(reviewer_stmt).all()
        for reviewer in reviewers:
            target_stmt = select(User).where(
                User.role == "user",
                User.is_active.is_(True),
                User.position_id == rule.target_position_id,
            )
            if rule.scope_type == "same_department":
                target_stmt = target_stmt.where(User.department_id == reviewer.department_id)
            else:
                target_department_ids = [item.department_id for item in rule.target_departments]
                if target_department_ids:
                    target_stmt = target_stmt.where(User.department_id.in_(target_department_ids))
            targets = db.scalars(target_stmt).all()
            for target in targets:
                if reviewer.id == target.id:
                    continue
                db.add(
                    EvaluationTask(
                        evaluation_id=evaluation.id,
                        reviewer_id=reviewer.id,
                        task_type="person",
                        rule_id=rule.id,
                        weight=rule.weight,
                        target_user_id=target.id,
                    )
                )
                created += 1

    department_rules = db.scalars(
        select(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == evaluation.id)
    ).all()
    for rule in department_rules:
        reviewers = db.scalars(
            select(User).where(
                User.role == "user",
                User.is_active.is_(True),
                User.position_id == rule.reviewer_position_id,
            )
        ).all()
        for reviewer in reviewers:
            db.add(
                EvaluationTask(
                    evaluation_id=evaluation.id,
                    reviewer_id=reviewer.id,
                    task_type="department",
                    rule_id=rule.id,
                    weight=rule.weight,
                    target_department_id=rule.target_department_id,
                )
            )
            created += 1

    evaluation.tasks_generated = True
    evaluation.archived = False
    db.commit()
    return created


def validate_vote_payload(db: Session, evaluation: Evaluation, reviewer: User, choices: dict[int, int]) -> list[str]:
    errors: list[str] = []
    if not evaluation.is_open:
        return ["当前不在考评期间，不能提交评分。"]
    tasks = db.scalars(
        select(EvaluationTask).where(
            EvaluationTask.evaluation_id == evaluation.id,
            EvaluationTask.reviewer_id == reviewer.id,
        )
    ).all()
    if not tasks:
        return ["当前没有分配给你的考核任务。"]
    submitted_count = db.scalar(
        select(func.count(EvaluationVote.id)).where(
            EvaluationVote.evaluation_id == evaluation.id,
            EvaluationVote.reviewer_id == reviewer.id,
        )
    )
    reopen = db.scalar(
        select(EvaluationReviewReopen).where(
            EvaluationReviewReopen.evaluation_id == evaluation.id,
            EvaluationReviewReopen.reviewer_id == reviewer.id,
        )
    )
    if submitted_count and not reopen:
        return ["你已经提交过本次考核，不能重复提交。"]
    task_ids = {task.id for task in tasks}
    if set(choices) != task_ids:
        errors.append("请完成所有评分项后再提交。")

    person_position_limit_rows = db.scalars(
        select(EvaluationPersonPositionOptionLimit)
        .where(EvaluationPersonPositionOptionLimit.evaluation_id == evaluation.id)
    ).all()
    person_limits = {
        (limit.target_position_id, limit.score_option_id): limit.max_people
        for limit in person_position_limit_rows
    }
    department_limits = {
        limit.score_option_id: limit.max_count
        for limit in db.scalars(
            select(EvaluationDepartmentOptionLimit)
            .where(EvaluationDepartmentOptionLimit.evaluation_id == evaluation.id)
        )
    }
    person_allowed = {option.id for option in evaluation_person_options(db, evaluation.id)}
    department_allowed = {option.id for option in evaluation_department_options(db, evaluation.id)}
    option_ids = set(choices.values())
    option_by_id = {
        option.id: option
        for option in db.scalars(select(ScoreOption).where(ScoreOption.id.in_(option_ids))).all()
    } if option_ids else {}
    position_by_id = {position.id: position for position in db.scalars(select(Position)).all()}
    person_counts: dict[tuple[int, int], int] = defaultdict(int)
    department_counts: dict[tuple[int, int], int] = defaultdict(int)
    for task in tasks:
        option_id = choices.get(task.id)
        if not option_id:
            continue
        if task.task_type == "person":
            target_position_id = task.target_user.position_id if task.target_user else None
            if not target_position_id:
                errors.append("评分选项不属于本次人员考核。")
                continue
            if option_id not in person_allowed:
                errors.append("评分选项不属于本次人员考核。")
                continue
            person_counts[(target_position_id, option_id)] += 1
        elif task.task_type == "department":
            if option_id not in department_allowed:
                errors.append("评分选项不属于本次部门考核。")
                continue
            department_counts[(0, option_id)] += 1
    for (target_position_id, option_id), count in person_counts.items():
        option = option_by_id.get(option_id)
        position = position_by_id.get(target_position_id)
        max_people = person_limits.get((target_position_id, option_id))
        if option and max_people is not None and count > max_people:
            position_name = position.name if position else "该职位"
            errors.append(f"“{option.name}”对“{position_name}”最多选择 {max_people} 人。")
    for (_, option_id), count in department_counts.items():
        option = option_by_id.get(option_id)
        max_people = department_limits.get(option_id)
        if option and max_people is not None and count > max_people:
            errors.append(f"“{option.name}”在部门考核中最多选择 {max_people} 个部门。")
    return errors


def submit_votes(db: Session, evaluation: Evaluation, reviewer: User, choices: dict[int, int]) -> None:
    errors = validate_vote_payload(db, evaluation, reviewer, choices)
    if errors:
        raise ValueError(errors[0])
    option_ids = set(choices.values())
    options = {
        option.id: option
        for option in db.scalars(select(ScoreOption).where(ScoreOption.id.in_(option_ids))).all()
    }
    tasks = db.scalars(
        select(EvaluationTask).where(
            EvaluationTask.evaluation_id == evaluation.id,
            EvaluationTask.reviewer_id == reviewer.id,
        )
    ).all()
    db.execute(
        delete(EvaluationVote).where(
            EvaluationVote.evaluation_id == evaluation.id,
            EvaluationVote.reviewer_id == reviewer.id,
        )
    )
    for task in tasks:
        option = options[choices[task.id]]
        task.submitted = True
        db.add(
            EvaluationVote(
                evaluation_id=evaluation.id,
                task_id=task.id,
                reviewer_id=reviewer.id,
                score_option_id=option.id,
                score_value=option.value,
            )
        )
    db.execute(
        delete(EvaluationReviewReopen).where(
            EvaluationReviewReopen.evaluation_id == evaluation.id,
            EvaluationReviewReopen.reviewer_id == reviewer.id,
        )
    )
    db.commit()


def calculate_evaluation_scores(db: Session, evaluation: Evaluation) -> dict:
    votes = db.scalars(
        select(EvaluationVote)
        .join(EvaluationTask, EvaluationTask.id == EvaluationVote.task_id)
        .where(EvaluationVote.evaluation_id == evaluation.id)
    ).all()
    person_scores: dict[int, float] = defaultdict(float)
    department_scores: dict[int, float] = defaultdict(float)
    score_groups: dict[tuple, dict] = {}
    details: list[dict] = []

    for vote in votes:
        task = vote.task
        reviewer = task.reviewer
        weighted = vote.score_value * task.weight
        if task.task_type == "person" and task.target_user:
            target = task.target_user
            target_id = target.id
            target_name = target.full_name
            department_name = target.department.name if target.department else ""
            position_name = target.position.name if target.position else ""
            rule = db.get(EvaluationPersonRule, task.rule_id)
            rule_label = ""
            if rule:
                departments = "、".join(item.department.name for item in rule.target_departments)
                if rule.scope_type == "same_department":
                    department_part = "（同部门）"
                else:
                    department_part = f"（{departments}）" if departments else ""
                rule_label = f"{rule.reviewer_position.name}评价{department_part}{rule.target_position.name}人员"
        elif task.task_type == "department" and task.target_department:
            target = task.target_department
            target_id = target.id
            target_name = target.name
            department_name = target.name
            position_name = ""
            rule = db.get(EvaluationDepartmentRule, task.rule_id)
            rule_label = ""
            if rule:
                rule_label = f"{rule.reviewer_position.name}评价{rule.target_department.name}部门"
        else:
            continue

        if task.task_type == "person" and rule:
            rule_group = (rule.score_group or "").strip()
            if not rule_group:
                rule_group = f"auto:{rule.reviewer_position_id}:{rule.target_position_id}:{task.weight}"
            group_key = ("person", rule_group, task.weight, target_id)
        else:
            group_key = (task.task_type, task.rule_id, target_id)
        if group_key not in score_groups:
            score_groups[group_key] = {
                "task_type": task.task_type,
                "target_id": target_id,
                "weight": task.weight,
                "scores": [],
            }
        score_groups[group_key]["scores"].append(vote.score_value)

        details.append({
            "task_type": task.task_type,
            "reviewer_id": reviewer.id,
            "reviewer_name": reviewer.full_name,
            "target_id": target_id,
            "target_name": target_name,
            "target_department_name": department_name,
            "target_position_name": position_name,
            "option_name": vote.option.name,
            "score_value": vote.score_value,
            "weight": task.weight,
            "weighted_score": weighted,
            "rule_label": rule_label,
        })

    for group in score_groups.values():
        scores = group["scores"]
        if not scores:
            continue
        contribution = (sum(scores) / len(scores)) * group["weight"]
        if group["task_type"] == "person":
            person_scores[group["target_id"]] += contribution
        elif group["task_type"] == "department":
            department_scores[group["target_id"]] += contribution

    share_rules = db.scalars(
        select(EvaluationDepartmentScoreShareRule).where(
            EvaluationDepartmentScoreShareRule.evaluation_id == evaluation.id
        )
    ).all()
    manual_department_scores = {
        item.department_id: item.score
        for item in db.scalars(
            select(EvaluationDepartmentManualScore).where(
                EvaluationDepartmentManualScore.evaluation_id == evaluation.id
            )
        )
    }
    department_final_scores = dict(department_scores)
    department_final_scores.update(manual_department_scores)

    for rule in share_rules:
        users = db.scalars(
            select(User).where(
                User.role == "user",
                User.is_active.is_(True),
                User.position_id == rule.target_position_id,
            )
        ).all()
        for user in users:
            if not user.department_id:
                continue
            department_score = department_final_scores.get(user.department_id)
            if department_score is None:
                continue
            person_scores[user.id] += department_score * rule.weight
            details.append({
                "task_type": "person",
                "reviewer_id": 0,
                "reviewer_name": "部门得分折算",
                "target_id": user.id,
                "target_name": user.full_name,
                "target_department_name": user.department.name if user.department else "",
                "target_position_name": user.position.name if user.position else "",
                "option_name": "部门得分",
                "score_value": round(department_score, 2),
                "weight": rule.weight,
                "weighted_score": round(department_score * rule.weight, 2),
                "rule_label": f"{user.department.name if user.department else '所在部门'}部门得分折算至{rule.target_position.name}",
            })

    people = []
    for user_id, final_score in person_scores.items():
        user = db.get(User, user_id)
        if user:
            people.append({
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "department_name": user.department.name if user.department else "",
                "position_name": user.position.name if user.position else "",
                "final_score": round(final_score, 2),
            })

    departments = []
    for department_id, final_score in department_final_scores.items():
        department = db.get(Department, department_id)
        if department:
            departments.append({
                "department_id": department.id,
                "department_name": department.name,
                "final_score": round(final_score, 2),
            })

    total_tasks = db.scalar(
        select(func.count(EvaluationTask.id)).where(EvaluationTask.evaluation_id == evaluation.id)
    ) or 0
    submitted_tasks = db.scalar(
        select(func.count(EvaluationVote.id)).where(EvaluationVote.evaluation_id == evaluation.id)
    ) or 0
    submitted_reviewers = db.scalar(
        select(func.count(func.distinct(EvaluationVote.reviewer_id))).where(
            EvaluationVote.evaluation_id == evaluation.id
        )
    ) or 0
    total_reviewers = db.scalar(
        select(func.count(func.distinct(EvaluationTask.reviewer_id))).where(
            EvaluationTask.evaluation_id == evaluation.id
        )
    ) or 0

    return {
        "people": sorted(people, key=lambda item: item["final_score"], reverse=True),
        "departments": sorted(departments, key=lambda item: item["final_score"], reverse=True),
        "details": details,
        "total_tasks": total_tasks,
        "submitted_tasks": submitted_tasks,
        "total_reviewers": total_reviewers,
        "submitted_reviewers": submitted_reviewers,
    }


def evaluation_task_progress(db: Session, evaluation_id: int) -> dict:
    total_tasks = db.scalar(
        select(func.count(EvaluationTask.id)).where(EvaluationTask.evaluation_id == evaluation_id)
    ) or 0
    submitted_tasks = db.scalar(
        select(func.count(EvaluationVote.id)).where(EvaluationVote.evaluation_id == evaluation_id)
    ) or 0
    pending_reopens = db.scalar(
        select(func.count(EvaluationReviewReopen.id)).where(EvaluationReviewReopen.evaluation_id == evaluation_id)
    ) or 0
    return {
        "total_tasks": total_tasks,
        "submitted_tasks": submitted_tasks,
        "pending_reopens": pending_reopens,
        "complete": total_tasks > 0 and submitted_tasks >= total_tasks and pending_reopens == 0,
    }


def archived_rule_snapshot_rows(db: Session, evaluation: Evaluation) -> list[ArchivedRuleSnapshot]:
    rows: list[ArchivedRuleSnapshot] = []
    person_options = [
        {"name": option.name, "value": option.value}
        for option in evaluation_person_options(db, evaluation.id)
    ]
    department_options = [
        {"name": option.name, "value": option.value}
        for option in evaluation_department_options(db, evaluation.id)
    ]
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="person_options",
        title="人员评分选项",
        payload=json.dumps(person_options, ensure_ascii=False),
    ))
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="department_options",
        title="部门评分选项",
        payload=json.dumps(department_options, ensure_ascii=False),
    ))

    person_limits = db.scalars(
        select(EvaluationPersonPositionOptionLimit)
        .where(EvaluationPersonPositionOptionLimit.evaluation_id == evaluation.id)
        .join(Position, Position.id == EvaluationPersonPositionOptionLimit.target_position_id)
        .join(ScoreOption, ScoreOption.id == EvaluationPersonPositionOptionLimit.score_option_id)
        .order_by(Position.sort_order, Position.id, ScoreOption.id)
    ).all()
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="person_limits",
        title="人员评分限制",
        payload=json.dumps([
            {
                "target_position": item.target_position.name,
                "option": item.option.name,
                "max_people": item.max_people,
            }
            for item in person_limits
        ], ensure_ascii=False),
    ))

    department_limits = db.scalars(
        select(EvaluationDepartmentOptionLimit)
        .where(EvaluationDepartmentOptionLimit.evaluation_id == evaluation.id)
        .join(ScoreOption, ScoreOption.id == EvaluationDepartmentOptionLimit.score_option_id)
        .order_by(ScoreOption.id)
    ).all()
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="department_limits",
        title="部门评分限制",
        payload=json.dumps([
            {"option": item.option.name, "max_count": item.max_count}
            for item in department_limits
        ], ensure_ascii=False),
    ))

    person_rules = db.scalars(select(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == evaluation.id)).all()
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="person_rules",
        title="人员考核规则",
        payload=json.dumps([
            {
                "reviewer_position": rule.reviewer_position.name,
                "reviewer_user": rule.reviewer_user.full_name if rule.reviewer_user else "",
                "target_position": rule.target_position.name,
                "score_group": rule.score_group,
                "scope_type": rule.scope_type,
                "target_departments": [item.department.name for item in rule.target_departments],
                "weight": rule.weight,
            }
            for rule in person_rules
        ], ensure_ascii=False),
    ))

    department_rules = db.scalars(select(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == evaluation.id)).all()
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="department_rules",
        title="部门考核规则",
        payload=json.dumps([
            {
                "reviewer_position": rule.reviewer_position.name,
                "target_department": rule.target_department.name,
                "weight": rule.weight,
            }
            for rule in department_rules
        ], ensure_ascii=False),
    ))

    share_rules = db.scalars(select(EvaluationDepartmentScoreShareRule).where(EvaluationDepartmentScoreShareRule.evaluation_id == evaluation.id)).all()
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="department_share_rules",
        title="部门得分占比规则",
        payload=json.dumps([
            {"target_position": rule.target_position.name, "weight": rule.weight}
            for rule in share_rules
        ], ensure_ascii=False),
    ))

    manual_scores = db.scalars(select(EvaluationDepartmentManualScore).where(EvaluationDepartmentManualScore.evaluation_id == evaluation.id)).all()
    rows.append(ArchivedRuleSnapshot(
        evaluation_id=evaluation.id,
        snapshot_type="manual_department_scores",
        title="手动部门得分",
        payload=json.dumps([
            {"department": item.department.name, "score": item.score}
            for item in manual_scores
        ], ensure_ascii=False),
    ))
    return rows


def archive_evaluation(db: Session, evaluation: Evaluation) -> None:
    progress = evaluation_task_progress(db, evaluation.id)
    if not progress["complete"]:
        raise ValueError("所有考核任务完成后才能归档。")
    db.execute(delete(ArchivedPersonScore).where(ArchivedPersonScore.evaluation_id == evaluation.id))
    db.execute(delete(ArchivedDepartmentScore).where(ArchivedDepartmentScore.evaluation_id == evaluation.id))
    db.execute(delete(ArchivedVoteDetail).where(ArchivedVoteDetail.evaluation_id == evaluation.id))
    db.execute(delete(ArchivedRuleSnapshot).where(ArchivedRuleSnapshot.evaluation_id == evaluation.id))

    result = calculate_evaluation_scores(db, evaluation)

    for detail in result["details"]:
        db.add(ArchivedVoteDetail(evaluation_id=evaluation.id, **detail))

    for person in result["people"]:
        db.add(ArchivedPersonScore(evaluation_id=evaluation.id, **person))

    for department in result["departments"]:
        db.add(ArchivedDepartmentScore(evaluation_id=evaluation.id, **department))

    for snapshot in archived_rule_snapshot_rows(db, evaluation):
        db.add(snapshot)

    evaluation.archived = True
    evaluation.is_open = False
    db.commit()
