import json
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import quote

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.master_data import department_choice_rows, departments_order, position_rows, positions_order
from app.api.schemas import EvaluationRow
from app.models import (
    ArchivedRuleSnapshot,
    Department,
    Evaluation,
    EvaluationAuditLog,
    EvaluationDepartmentManualScore,
    EvaluationDepartmentOptionLimit,
    EvaluationDepartmentRule,
    EvaluationDepartmentScoreOption,
    EvaluationDepartmentScoreShareRule,
    EvaluationPersonPositionOptionLimit,
    EvaluationPersonRule,
    EvaluationPersonRuleDepartment,
    EvaluationScoreOption,
    EvaluationTask,
    Position,
    ScoreOption,
    User,
)
from app.services import (
    evaluation_department_options,
    evaluation_person_options,
    evaluation_task_progress,
)

def decimal_input(value, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name}格式不正确。") from exc


def ensure_editable(evaluation: Evaluation) -> None:
    if evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已归档考核不能再修改。")


def require_evaluation(db: Session, evaluation_id: int) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="考核不存在。")
    return evaluation


def require_evaluation_for_update(db: Session, evaluation_id: int) -> Evaluation:
    evaluation = db.scalar(select(Evaluation).where(Evaluation.id == evaluation_id).with_for_update())
    if not evaluation:
        raise HTTPException(status_code=404, detail="考核不存在。")
    return evaluation


def snapshot_payload(payload: str) -> list[dict]:
    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def archived_snapshots(db: Session, evaluation_id: int) -> dict[str, list[dict]]:
    rows = db.scalars(select(ArchivedRuleSnapshot).where(ArchivedRuleSnapshot.evaluation_id == evaluation_id)).all()
    return {row.snapshot_type: snapshot_payload(row.payload) for row in rows}


def archived_config_payload(db: Session, evaluation: Evaluation) -> dict:
    data = archived_snapshots(db, evaluation.id)
    person_options = data.get("person_options", [])
    department_options = data.get("department_options", [])
    option_rows = person_options + [item for item in department_options if item.get("source_score_option_id") not in {row.get("source_score_option_id") for row in person_options}]
    return {
        "evaluation": evaluation_row(db, evaluation), "positions": [], "departments": [],
        "score_options": [{"id": row.get("source_score_option_id", i + 1), "name": row.get("name", ""), "value": row.get("value", 0)} for i, row in enumerate(option_rows)],
        "person_option_ids": [row.get("source_score_option_id", i + 1) for i, row in enumerate(person_options)],
        "department_option_ids": [row.get("source_score_option_id", i + 1) for i, row in enumerate(department_options)],
        "person_rules": [{
            "id": i + 1, "reviewer_position_id": row.get("source_reviewer_position_id"), "reviewer_position_name": row.get("reviewer_position", ""),
            "reviewer_user_id": row.get("source_reviewer_user_id"), "reviewer_user_name": row.get("reviewer_user", ""),
            "target_position_id": row.get("source_target_position_id"), "target_position_name": row.get("target_position", ""),
            "score_group": row.get("score_group", ""), "scope_type": row.get("scope_type", "selected_departments"),
            "target_department_ids": row.get("source_target_department_ids", []),
            "target_department_label": "、".join(row.get("target_departments", [])) or ("同部门" if row.get("scope_type") == "same_department" else "全部"),
            "weight": row.get("weight", 0),
        } for i, row in enumerate(data.get("person_rules", []))],
        "department_rules": [{"id": i + 1, "reviewer_position_id": row.get("source_reviewer_position_id"), "reviewer_position_name": row.get("reviewer_position", ""), "target_department_id": row.get("source_target_department_id"), "target_department_name": row.get("target_department", ""), "weight": row.get("weight", 0)} for i, row in enumerate(data.get("department_rules", []))],
        "person_limits": [{"id": i + 1, "target_position_id": row.get("source_target_position_id"), "target_position_name": row.get("target_position", ""), "score_option_id": row.get("source_score_option_id"), "score_option_name": row.get("option", ""), "max_people": row.get("max_people")} for i, row in enumerate(data.get("person_limits", []))],
        "department_limits": [{"id": i + 1, "score_option_id": row.get("source_score_option_id"), "score_option_name": row.get("option", ""), "max_count": row.get("max_count")} for i, row in enumerate(data.get("department_limits", []))],
        "share_rules": [{"id": i + 1, "target_position_id": row.get("source_target_position_id"), "target_position_name": row.get("target_position", ""), "weight": row.get("weight", 0)} for i, row in enumerate(data.get("department_share_rules", []))],
        "manual_scores": [{"id": i + 1, "department_id": row.get("source_department_id"), "department_name": row.get("department", ""), "score": row.get("score", 0)} for i, row in enumerate(data.get("manual_department_scores", []))],
    }


def score_workbook(sheet_title: str, headers: list[str], rows: list[list[object]]) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    header_fill = PatternFill("solid", fgColor="DCEBFF")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="102F5F")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column) + 4
        sheet.column_dimensions[column[0].column_letter].width = min(max(width, 12), 36)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def excel_response(content: BytesIO, filename: str) -> StreamingResponse:
    encoded = quote(filename)
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


def add_audit_log(db: Session, evaluation_id: int, user: User | None, action: str, detail: str = "") -> None:
    db.add(EvaluationAuditLog(
        evaluation_id=evaluation_id,
        actor_id=user.id if user else None,
        actor_name=user.full_name if user else "",
        action=action,
        detail=detail,
    ))


def evaluation_row(db: Session, evaluation: Evaluation) -> EvaluationRow:
    progress = evaluation_task_progress(db, evaluation.id)
    return EvaluationRow(
        id=evaluation.id,
        name=evaluation.name,
        year=evaluation.year,
        sequence=evaluation.sequence,
        is_open=evaluation.is_open,
        tasks_generated=evaluation.tasks_generated,
        archived=evaluation.archived,
        total_tasks=progress["total_tasks"],
        submitted_tasks=progress["submitted_tasks"],
        pending_reopens=progress["pending_reopens"],
    )


def current_open_evaluation(db: Session) -> Evaluation | None:
    return db.scalar(
        select(Evaluation)
        .where(Evaluation.is_open.is_(True))
        .order_by(Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.id.desc())
    )


def task_limit_map(db: Session, evaluation_id: int) -> dict[str, int]:
    limits: dict[str, int] = {}
    person_limits = db.scalars(
        select(EvaluationPersonPositionOptionLimit)
        .where(EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id)
    ).all()
    for item in person_limits:
        if item.max_people is not None:
            limits[f"person:{item.target_position_id}:{item.score_option_id}"] = item.max_people
    department_limits = db.scalars(
        select(EvaluationDepartmentOptionLimit)
        .where(EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id)
    ).all()
    for item in department_limits:
        if item.max_count is not None:
            limits[f"department:all:{item.score_option_id}"] = item.max_count
    return limits


def score_limit_text(db: Session, evaluation_id: int | None, group_type: str, position_id: int | None = None) -> str:
    if not evaluation_id:
        return "不限制"
    if group_type == "person":
        options = evaluation_person_options(db, evaluation_id)
        rows = db.scalars(
            select(EvaluationPersonPositionOptionLimit).where(
                EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id,
                EvaluationPersonPositionOptionLimit.target_position_id == position_id,
                EvaluationPersonPositionOptionLimit.max_people.is_not(None),
            )
        ).all()
        unit = "人"
        limit_map = {row.score_option_id: row.max_people for row in rows}
    else:
        options = evaluation_department_options(db, evaluation_id)
        rows = db.scalars(
            select(EvaluationDepartmentOptionLimit).where(
                EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id,
                EvaluationDepartmentOptionLimit.max_count.is_not(None),
            )
        ).all()
        unit = "个"
        limit_map = {row.score_option_id: row.max_count for row in rows}

    parts = [
        f"{option.name}最多 {limit_map[option.id]} {unit}"
        for option in options
        if option.id in limit_map
    ]
    return "；".join(parts) if parts else "不限制"


def option_payload(options: list[ScoreOption]) -> list[dict]:
    return [{"id": option.id, "name": option.name} for option in options]


def task_payload(task: EvaluationTask) -> dict:
    target = task.target_user if task.task_type == "person" else task.target_department
    if task.task_type == "person" and task.target_user:
        department_name = task.target_user.department.name if task.target_user.department else ""
        position_name = task.target_user.position.name if task.target_user.position else ""
        target_name = task.target_user.full_name
    elif task.target_department:
        department_name = task.target_department.name
        position_name = ""
        target_name = task.target_department.name
    else:
        department_name = ""
        position_name = ""
        target_name = ""
    return {
        "id": task.id,
        "task_type": task.task_type,
        "target_id": getattr(target, "id", None),
        "target_name": target_name,
        "department_name": department_name,
        "position_name": position_name,
        "submitted": task.submitted,
        "limit_key_rule": task.target_user.position_id if task.task_type == "person" and task.target_user else "all",
    }


def task_groups(db: Session, tasks: list[EvaluationTask]) -> list[dict]:
    evaluation_ids = {task.evaluation_id for task in tasks}
    evaluation_id = next(iter(evaluation_ids), None)
    person_options = evaluation_person_options(db, evaluation_id) if evaluation_id else []
    department_options = evaluation_department_options(db, evaluation_id) if evaluation_id else []
    positions = db.scalars(select(Position).order_by(*positions_order())).all()
    position_order = {position.id: index for index, position in enumerate(positions)}
    position_names = {position.id: position.name for position in positions}
    departments = db.scalars(select(Department).order_by(*departments_order())).all()
    department_order = {department.id: index for index, department in enumerate(departments)}

    person_tasks = [task for task in tasks if task.task_type == "person" and task.target_user]
    department_tasks = [task for task in tasks if task.task_type == "department" and task.target_department]
    person_tasks.sort(
        key=lambda task: (
            position_order.get(task.target_user.position_id, 10_000),
            department_order.get(task.target_user.department_id, 10_000),
            task.target_user.full_name,
            task.id,
        )
    )
    department_tasks.sort(
        key=lambda task: (
            department_order.get(task.target_department_id, 10_000),
            task.target_department.name if task.target_department else "",
            task.id,
        )
    )

    groups: list[dict] = []
    grouped_person_tasks: dict[int | None, list[EvaluationTask]] = {}
    for task in person_tasks:
        grouped_person_tasks.setdefault(task.target_user.position_id, []).append(task)
    for position_id, grouped_tasks in grouped_person_tasks.items():
        groups.append({
            "type": "person",
            "title": f"被评对象：{position_names.get(position_id, '未设置职位')}",
            "limit_text": score_limit_text(db, evaluation_id, "person", position_id),
            "options": option_payload(person_options),
            "tasks": [task_payload(task) for task in grouped_tasks],
        })
    if department_tasks:
        groups.append({
            "type": "department",
            "title": "部门考核",
            "limit_text": score_limit_text(db, evaluation_id, "department"),
            "options": option_payload(department_options),
            "tasks": [task_payload(task) for task in department_tasks],
        })
    return groups


def selected_reviewer_user_id(db: Session, reviewer_user_id: int | None, reviewer_position_id: int) -> int | None:
    if not reviewer_user_id:
        return None
    reviewer = db.get(User, reviewer_user_id)
    if not reviewer or reviewer.role != "user" or not reviewer.is_active or reviewer.position_id != reviewer_position_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="指定评价人必须是所选评分人职位下的启用普通用户。")
    return reviewer.id


def person_rule_scope(payload: dict) -> tuple[str, list[int]]:
    scope_type = payload.get("scope_type") or "selected_departments"
    if scope_type not in {"selected_departments", "same_department"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="评价范围无效。")
    if scope_type == "same_department":
        return scope_type, []
    department_ids = [int(department_id) for department_id in payload.get("target_department_ids") or []]
    if not department_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择被评部门范围。")
    return scope_type, list(dict.fromkeys(department_ids))


def save_person_options(db: Session, evaluation_id: int, option_ids: list[int]) -> None:
    db.execute(delete(EvaluationScoreOption).where(EvaluationScoreOption.evaluation_id == evaluation_id))
    for index, option_id in enumerate(option_ids):
        db.add(EvaluationScoreOption(evaluation_id=evaluation_id, score_option_id=option_id, sort_order=index))
    if option_ids:
        db.execute(
            delete(EvaluationPersonPositionOptionLimit).where(
                EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id,
                EvaluationPersonPositionOptionLimit.score_option_id.not_in(option_ids),
            )
        )
    else:
        db.execute(delete(EvaluationPersonPositionOptionLimit).where(EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id))


def save_department_options(db: Session, evaluation_id: int, option_ids: list[int]) -> None:
    db.execute(delete(EvaluationDepartmentScoreOption).where(EvaluationDepartmentScoreOption.evaluation_id == evaluation_id))
    for index, option_id in enumerate(option_ids):
        db.add(EvaluationDepartmentScoreOption(evaluation_id=evaluation_id, score_option_id=option_id, sort_order=index))
    if option_ids:
        db.execute(
            delete(EvaluationDepartmentOptionLimit).where(
                EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id,
                EvaluationDepartmentOptionLimit.score_option_id.not_in(option_ids),
            )
        )
    else:
        db.execute(delete(EvaluationDepartmentOptionLimit).where(EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id))


def evaluation_config_payload(db: Session, evaluation: Evaluation) -> dict:
    positions = position_rows(db)
    departments = department_choice_rows(db)
    score_options = [{"id": item.id, "name": item.name, "value": item.value} for item in db.scalars(select(ScoreOption).order_by(ScoreOption.id)).all()]
    person_options = evaluation_person_options(db, evaluation.id)
    department_options = evaluation_department_options(db, evaluation.id)
    department_labels = {item["id"]: item["display_name"] for item in departments}
    person_rules = []
    for rule in db.scalars(select(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == evaluation.id).order_by(EvaluationPersonRule.id)).all():
        person_rules.append({
            "id": rule.id,
            "reviewer_position_id": rule.reviewer_position_id,
            "reviewer_position_name": rule.reviewer_position.name,
            "reviewer_user_id": rule.reviewer_user_id,
            "reviewer_user_name": rule.reviewer_user.full_name if rule.reviewer_user else "",
            "target_position_id": rule.target_position_id,
            "target_position_name": rule.target_position.name,
            "score_group": rule.score_group,
            "scope_type": rule.scope_type,
            "target_department_ids": [item.department_id for item in rule.target_departments],
            "target_department_label": "、".join(department_labels.get(item.department_id, "") for item in rule.target_departments) or ("同部门" if rule.scope_type == "same_department" else "全部"),
            "weight": rule.weight,
        })
    department_rules = []
    for rule in db.scalars(select(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == evaluation.id).order_by(EvaluationDepartmentRule.id)).all():
        department_rules.append({
            "id": rule.id,
            "reviewer_position_id": rule.reviewer_position_id,
            "reviewer_position_name": rule.reviewer_position.name,
            "target_department_id": rule.target_department_id,
            "target_department_name": department_labels.get(rule.target_department_id, rule.target_department.name),
            "weight": rule.weight,
        })
    person_limits = [
        {
            "id": item.id,
            "target_position_id": item.target_position_id,
            "target_position_name": item.target_position.name,
            "score_option_id": item.score_option_id,
            "score_option_name": item.option.name,
            "max_people": item.max_people,
        }
        for item in db.scalars(
            select(EvaluationPersonPositionOptionLimit)
            .where(EvaluationPersonPositionOptionLimit.evaluation_id == evaluation.id)
            .order_by(EvaluationPersonPositionOptionLimit.id)
        ).all()
    ]
    department_limits = [
        {
            "id": item.id,
            "score_option_id": item.score_option_id,
            "score_option_name": item.option.name,
            "max_count": item.max_count,
        }
        for item in db.scalars(
            select(EvaluationDepartmentOptionLimit)
            .where(EvaluationDepartmentOptionLimit.evaluation_id == evaluation.id)
            .order_by(EvaluationDepartmentOptionLimit.id)
        ).all()
    ]
    share_rules = [
        {
            "id": item.id,
            "target_position_id": item.target_position_id,
            "target_position_name": item.target_position.name,
            "weight": item.weight,
        }
        for item in db.scalars(
            select(EvaluationDepartmentScoreShareRule)
            .where(EvaluationDepartmentScoreShareRule.evaluation_id == evaluation.id)
            .order_by(EvaluationDepartmentScoreShareRule.id)
        ).all()
    ]
    manual_scores = [
        {
            "id": item.id,
            "department_id": item.department_id,
            "department_name": item.department.name,
            "score": item.score,
        }
        for item in db.scalars(
            select(EvaluationDepartmentManualScore)
            .where(EvaluationDepartmentManualScore.evaluation_id == evaluation.id)
            .order_by(EvaluationDepartmentManualScore.id)
        ).all()
    ]
    return {
        "evaluation": evaluation_row(db, evaluation),
        "positions": positions,
        "departments": departments,
        "score_options": score_options,
        "person_option_ids": [item.id for item in person_options],
        "department_option_ids": [item.id for item in department_options],
        "person_rules": person_rules,
        "department_rules": department_rules,
        "person_limits": person_limits,
        "department_limits": department_limits,
        "share_rules": share_rules,
        "manual_scores": manual_scores,
    }

