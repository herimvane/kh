import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import Integer, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.admin_scope import (
    ensure_department_manageable,
    ensure_departments_manageable,
    evaluation_scope_values,
    manageable_department_ids,
)
from app.api.deps import require_api_admin, require_api_user, require_super_admin
from app.api.evaluation_helpers import (
    add_audit_log,
    archived_config_payload,
    archived_snapshots,
    decimal_input,
    ensure_editable,
    ensure_result_editable,
    evaluation_config_payload,
    evaluation_row,
    excel_response,
    person_rule_scope,
    require_evaluation,
    require_evaluation_for_update,
    save_department_options,
    save_person_options,
    score_workbook,
    selected_reviewer_user_id,
    snapshot_payload,
    task_groups,
    task_limit_map,
)
from app.api.master_data import department_choice_rows, departments_order, pagination, position_rows, positions_order
from app.api.schemas import EvaluationActionResponse, EvaluationCreate, EvaluationRow, MessageResponse, ScoreDetailPasswordRequest, VoteSubmitRequest
from app.config import score_detail_password_hash
from app.database import get_db
from app.models import (
    ArchivedDepartmentScore,
    ArchivedPersonScore,
    ArchivedRuleSnapshot,
    ArchivedSubmission,
    ArchivedVoteDetail,
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
    EvaluationReviewReopen,
    EvaluationScoreOption,
    EvaluationTask,
    EvaluationVote,
    Position,
    ScoreOption,
    User,
)
from app.services import (
    archive_evaluation,
    calculate_evaluation_scores,
    evaluation_department_options,
    evaluation_person_options,
    evaluation_task_progress,
    generate_tasks,
    submit_votes,
)
from app.security import verify_password

router = APIRouter(tags=["evaluations"])



@router.get("/evaluations", response_model=list[EvaluationRow])
def list_evaluations(db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    stmt = select(Evaluation)
    allowed = manageable_department_ids(db, user)
    if allowed is not None:
        stmt = stmt.where(Evaluation.owner_department_id.in_(allowed))
    evaluations = db.scalars(
        stmt.order_by(Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.created_at.desc(), Evaluation.id.desc())
    ).all()
    return [evaluation_row(db, evaluation) for evaluation in evaluations]


def next_evaluation_sequence(db: Session, year: int, scope_key: str) -> int:
    current = db.scalar(
        select(func.max(Evaluation.sequence)).where(
            Evaluation.year == year,
            Evaluation.scope_key == scope_key,
        )
    ) or 0
    return int(current) + 1


@router.post("/evaluations", response_model=EvaluationRow, status_code=status.HTTP_201_CREATED)
def create_evaluation(payload: EvaluationCreate, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    scope_key, owner_department_id, owner_name = evaluation_scope_values(db, user, payload.owner_department_id)
    sequence = payload.sequence if payload.sequence is not None else next_evaluation_sequence(db, payload.year, scope_key)
    if sequence < 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="年内批次必须大于 0。")
    evaluation = Evaluation(
        year=payload.year,
        sequence=sequence,
        name=payload.name.strip() or f"{payload.year}-{sequence:02d}",
        scope_key=scope_key,
        owner_department_id=owner_department_id,
        owner_department_name_snapshot=owner_name,
        created_by_id=user.id,
    )
    db.add(evaluation)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        scope_label = "" if scope_key == "GLOBAL" else f"{owner_name}下 "
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{scope_label}{payload.year} 年第 {sequence} 批考核已存在。",
        ) from exc
    add_audit_log(db, evaluation.id, user, "新增考核", f"年度：{evaluation.year}；批次：{evaluation.sequence}")
    db.commit()
    return evaluation_row(db, evaluation)


@router.get("/evaluations/audit")
def evaluations_audit(q: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    start_year = datetime.utcnow().year - 2
    rows_stmt = (
        select(EvaluationAuditLog, Evaluation.name.label("evaluation_name"), Evaluation.year.label("evaluation_year"))
        .join(Evaluation, Evaluation.id == EvaluationAuditLog.evaluation_id)
        .where(Evaluation.year >= start_year)
    )
    allowed = manageable_department_ids(db, user)
    if allowed is not None:
        rows_stmt = rows_stmt.where(Evaluation.owner_department_id.in_(allowed))
    if q:
        like = f"%{q}%"
        rows_stmt = rows_stmt.where(or_(
            Evaluation.name.like(like),
            EvaluationAuditLog.actor_name.like(like),
            EvaluationAuditLog.action.like(like),
            EvaluationAuditLog.detail.like(like),
        ))
    rows_stmt = rows_stmt.order_by(EvaluationAuditLog.id.desc())
    total = db.scalar(select(func.count()).select_from(rows_stmt.order_by(None).subquery())) or 0
    page_info = pagination(total, page, 20)
    rows = db.execute(rows_stmt.offset((page_info.page - 1) * page_info.page_size).limit(page_info.page_size)).all()
    return {
        "items": [
            {
                "id": log.id,
                "evaluation_name": evaluation_name,
                "evaluation_year": evaluation_year,
                "actor_name": log.actor_name,
                "action": log.action,
                "detail": log.detail,
                "created_at": log.created_at.isoformat(),
            }
            for log, evaluation_name, evaluation_year in rows
        ],
        "pagination": page_info,
        "start_year": start_year,
    }


@router.get("/evaluations/{evaluation_id}/config")
def evaluation_config(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    return archived_config_payload(db, evaluation) if evaluation.archived else evaluation_config_payload(db, evaluation, user)


@router.put("/evaluations/{evaluation_id}/person-options", response_model=MessageResponse)
def update_person_options(evaluation_id: int, option_ids: list[int], db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    save_person_options(db, evaluation_id, option_ids)
    add_audit_log(db, evaluation_id, user, "保存人员评分选项", f"选项数量：{len(option_ids)}")
    db.commit()
    return MessageResponse(message="人员评分选项已保存。")


@router.put("/evaluations/{evaluation_id}/department-options", response_model=MessageResponse)
def update_department_options(evaluation_id: int, option_ids: list[int], db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    save_department_options(db, evaluation_id, option_ids)
    add_audit_log(db, evaluation_id, user, "保存部门评分选项", f"选项数量：{len(option_ids)}")
    db.commit()
    return MessageResponse(message="部门评分选项已保存。")


@router.post("/evaluations/{evaluation_id}/person-limits", response_model=MessageResponse)
def upsert_person_limit(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    target_position_id = int(payload["target_position_id"])
    score_option_id = int(payload["score_option_id"])
    max_people = payload.get("max_people")
    max_value = int(max_people) if max_people not in (None, "") else None
    existing = db.scalar(select(EvaluationPersonPositionOptionLimit).where(
        EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id,
        EvaluationPersonPositionOptionLimit.target_position_id == target_position_id,
        EvaluationPersonPositionOptionLimit.score_option_id == score_option_id,
    ))
    if existing:
        if max_value is None:
            db.delete(existing)
        else:
            existing.max_people = max_value
    elif max_value is not None:
        db.add(EvaluationPersonPositionOptionLimit(evaluation_id=evaluation_id, target_position_id=target_position_id, score_option_id=score_option_id, max_people=max_value))
    add_audit_log(db, evaluation_id, user, "保存人员评分限制", f"职位ID：{target_position_id}；评分项ID：{score_option_id}；限制：{max_value}")
    db.commit()
    return MessageResponse(message="人员评分限制已保存。")


@router.delete("/evaluations/{evaluation_id}/person-limits/{limit_id}", response_model=MessageResponse)
def delete_person_limit(evaluation_id: int, limit_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    limit = db.get(EvaluationPersonPositionOptionLimit, limit_id)
    if limit and limit.evaluation_id == evaluation_id:
        db.delete(limit)
        add_audit_log(db, evaluation_id, user, "删除人员评分限制", f"限制ID：{limit_id}")
        db.commit()
    return MessageResponse(message="人员评分限制已删除。")


@router.post("/evaluations/{evaluation_id}/department-limits", response_model=MessageResponse)
def upsert_department_limit(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    score_option_id = int(payload["score_option_id"])
    max_count = payload.get("max_count")
    max_value = int(max_count) if max_count not in (None, "") else None
    enabled = db.scalar(select(EvaluationDepartmentScoreOption).where(EvaluationDepartmentScoreOption.evaluation_id == evaluation_id, EvaluationDepartmentScoreOption.score_option_id == score_option_id))
    if not enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先保存该部门评分选项后再设置数量限制。")
    existing = db.scalar(select(EvaluationDepartmentOptionLimit).where(EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id, EvaluationDepartmentOptionLimit.score_option_id == score_option_id))
    if existing:
        if max_value is None:
            db.delete(existing)
        else:
            existing.max_count = max_value
    elif max_value is not None:
        db.add(EvaluationDepartmentOptionLimit(evaluation_id=evaluation_id, score_option_id=score_option_id, max_count=max_value))
    add_audit_log(db, evaluation_id, user, "保存部门评分限制", f"评分项ID：{score_option_id}；限制：{max_value}")
    db.commit()
    return MessageResponse(message="部门评分限制已保存。")


@router.delete("/evaluations/{evaluation_id}/department-limits/{limit_id}", response_model=MessageResponse)
def delete_department_limit(evaluation_id: int, limit_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    limit = db.get(EvaluationDepartmentOptionLimit, limit_id)
    if limit and limit.evaluation_id == evaluation_id:
        db.delete(limit)
        add_audit_log(db, evaluation_id, user, "删除部门评分限制", f"限制ID：{limit_id}")
        db.commit()
    return MessageResponse(message="部门评分限制已删除。")


@router.post("/evaluations/{evaluation_id}/person-rules", response_model=MessageResponse)
def create_person_rule(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    reviewer_position_id = int(payload["reviewer_position_id"])
    scope_type, department_ids = person_rule_scope(payload)
    ensure_departments_manageable(db, user, department_ids)
    rule = EvaluationPersonRule(
        evaluation_id=evaluation_id,
        reviewer_position_id=reviewer_position_id,
        reviewer_user_id=selected_reviewer_user_id(db, payload.get("reviewer_user_id"), reviewer_position_id, user),
        target_position_id=int(payload["target_position_id"]),
        score_group=(payload.get("score_group") or "").strip(),
        scope_type=scope_type,
        weight=decimal_input(payload["weight"], "权重"),
    )
    db.add(rule)
    db.flush()
    for department_id in department_ids:
        db.add(EvaluationPersonRuleDepartment(rule_id=rule.id, department_id=department_id))
    add_audit_log(db, evaluation_id, user, "新增人员考核规则", f"规则ID：{rule.id}")
    db.commit()
    return MessageResponse(message="人员考核规则已添加。")


@router.put("/evaluations/{evaluation_id}/person-rules/{rule_id}", response_model=MessageResponse)
def update_person_rule(evaluation_id: int, rule_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    rule = db.get(EvaluationPersonRule, rule_id)
    if not rule or rule.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404, detail="规则不存在。")
    reviewer_position_id = int(payload["reviewer_position_id"])
    scope_type, department_ids = person_rule_scope(payload)
    ensure_departments_manageable(db, user, department_ids)
    rule.reviewer_position_id = reviewer_position_id
    rule.reviewer_user_id = selected_reviewer_user_id(db, payload.get("reviewer_user_id"), reviewer_position_id, user)
    rule.target_position_id = int(payload["target_position_id"])
    rule.score_group = (payload.get("score_group") or "").strip()
    rule.scope_type = scope_type
    rule.weight = decimal_input(payload["weight"], "权重")
    db.execute(delete(EvaluationPersonRuleDepartment).where(EvaluationPersonRuleDepartment.rule_id == rule.id))
    for department_id in department_ids:
        db.add(EvaluationPersonRuleDepartment(rule_id=rule.id, department_id=department_id))
    add_audit_log(db, evaluation_id, user, "更新人员考核规则", f"规则ID：{rule_id}")
    db.commit()
    return MessageResponse(message="人员考核规则已更新。")


@router.delete("/evaluations/{evaluation_id}/person-rules/{rule_id}", response_model=MessageResponse)
def delete_person_rule(evaluation_id: int, rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    rule = db.get(EvaluationPersonRule, rule_id)
    if rule and rule.evaluation_id == evaluation_id:
        db.delete(rule)
        add_audit_log(db, evaluation_id, user, "删除人员考核规则", f"规则ID：{rule_id}")
        db.commit()
    return MessageResponse(message="人员考核规则已删除。")


@router.post("/evaluations/{evaluation_id}/department-rules", response_model=MessageResponse)
def create_department_rule(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    department_ids = list(dict.fromkeys(int(item) for item in (payload.get("target_department_ids") or [])))
    if not department_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请选择被评部门。")
    ensure_departments_manageable(db, user, set(department_ids))
    group_key = str(uuid4())
    reviewer_position_id = int(payload["reviewer_position_id"])
    weight = decimal_input(payload["weight"], "权重")
    for department_id in department_ids:
        db.add(EvaluationDepartmentRule(evaluation_id=evaluation_id, group_key=group_key, reviewer_position_id=reviewer_position_id, target_department_id=department_id, weight=weight))
    add_audit_log(db, evaluation_id, user, "新增部门考核规则", f"部门数量：{len(department_ids)}")
    db.commit()
    return MessageResponse(message="部门考核规则已添加。")


@router.put("/evaluations/{evaluation_id}/department-rules/{rule_id}", response_model=MessageResponse)
def update_department_rule(evaluation_id: int, rule_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    rule = db.get(EvaluationDepartmentRule, rule_id)
    if not rule or rule.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404, detail="规则不存在。")
    department_ids = list(dict.fromkeys(int(item) for item in (payload.get("target_department_ids") or [])))
    if not department_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请选择被评部门。")
    ensure_departments_manageable(db, user, set(department_ids))
    group_key = rule.group_key
    grouped_rules = db.scalars(
        select(EvaluationDepartmentRule)
        .where(EvaluationDepartmentRule.evaluation_id == evaluation_id, EvaluationDepartmentRule.group_key == group_key)
        .order_by(EvaluationDepartmentRule.id)
    ).all()
    primary_rule = grouped_rules[0]
    reviewer_position_id = int(payload["reviewer_position_id"])
    weight = decimal_input(payload["weight"], "权重")
    primary_rule.reviewer_position_id = reviewer_position_id
    primary_rule.target_department_id = department_ids[0]
    primary_rule.weight = weight
    for extra_rule in grouped_rules[1:]:
        db.delete(extra_rule)
    for department_id in department_ids[1:]:
        db.add(EvaluationDepartmentRule(evaluation_id=evaluation_id, group_key=group_key, reviewer_position_id=reviewer_position_id, target_department_id=department_id, weight=weight))
    add_audit_log(db, evaluation_id, user, "更新部门考核规则", f"规则组：{group_key}；部门数量：{len(department_ids)}")
    db.commit()
    return MessageResponse(message="部门考核规则已更新。")


@router.delete("/evaluations/{evaluation_id}/department-rules/{rule_id}", response_model=MessageResponse)
def delete_department_rule(evaluation_id: int, rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    rule = db.get(EvaluationDepartmentRule, rule_id)
    if rule and rule.evaluation_id == evaluation_id:
        group_key = rule.group_key
        grouped_rules = db.scalars(
            select(EvaluationDepartmentRule).where(
                EvaluationDepartmentRule.evaluation_id == evaluation_id,
                EvaluationDepartmentRule.group_key == group_key,
            )
        ).all()
        for grouped_rule in grouped_rules:
            db.delete(grouped_rule)
        add_audit_log(db, evaluation_id, user, "删除部门考核规则", f"规则组：{group_key}；部门数量：{len(grouped_rules)}")
        db.commit()
    return MessageResponse(message="部门考核规则已删除。")


@router.post("/evaluations/{evaluation_id}/share-rules", response_model=MessageResponse)
def upsert_share_rule(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    target_position_id = int(payload["target_position_id"])
    weight = decimal_input(payload["weight"], "权重")
    existing = db.scalar(select(EvaluationDepartmentScoreShareRule).where(EvaluationDepartmentScoreShareRule.evaluation_id == evaluation_id, EvaluationDepartmentScoreShareRule.target_position_id == target_position_id))
    if existing:
        existing.weight = weight
    else:
        db.add(EvaluationDepartmentScoreShareRule(evaluation_id=evaluation_id, target_position_id=target_position_id, weight=weight))
    add_audit_log(db, evaluation_id, user, "保存部门得分占比规则", f"职位ID：{target_position_id}；权重：{weight}")
    db.commit()
    return MessageResponse(message="部门得分占比规则已保存。")


@router.delete("/evaluations/{evaluation_id}/share-rules/{rule_id}", response_model=MessageResponse)
def delete_share_rule(evaluation_id: int, rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_editable(evaluation)
    rule = db.get(EvaluationDepartmentScoreShareRule, rule_id)
    if rule and rule.evaluation_id == evaluation_id:
        db.delete(rule)
        add_audit_log(db, evaluation_id, user, "删除部门得分占比规则", f"规则ID：{rule_id}")
        db.commit()
    return MessageResponse(message="部门得分占比规则已删除。")


@router.post("/evaluations/{evaluation_id}/manual-department-scores", response_model=MessageResponse)
def upsert_manual_score(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_result_editable(evaluation)
    department_id = int(payload["department_id"])
    ensure_departments_manageable(db, user, [department_id])
    score = decimal_input(payload["score"], "得分")
    existing = db.scalar(select(EvaluationDepartmentManualScore).where(EvaluationDepartmentManualScore.evaluation_id == evaluation_id, EvaluationDepartmentManualScore.department_id == department_id))
    if existing:
        existing.score = score
    else:
        db.add(EvaluationDepartmentManualScore(evaluation_id=evaluation_id, department_id=department_id, score=score))
    add_audit_log(db, evaluation_id, user, "保存手动部门得分", f"部门ID：{department_id}；得分：{score}")
    db.commit()
    return MessageResponse(message="手动部门得分已保存。")


@router.delete("/evaluations/{evaluation_id}/manual-department-scores/{score_id}", response_model=MessageResponse)
def delete_manual_score(evaluation_id: int, score_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    ensure_result_editable(evaluation)
    item = db.get(EvaluationDepartmentManualScore, score_id)
    if item and item.evaluation_id == evaluation_id:
        db.delete(item)
        add_audit_log(db, evaluation_id, user, "删除手动部门得分", f"记录ID：{score_id}")
        db.commit()
    return MessageResponse(message="手动部门得分已删除。")


def archived_copy_missing(db: Session, evaluation_id: int) -> list[dict]:
    data = archived_snapshots(db, evaluation_id)
    missing: dict[tuple[str, int], dict] = {}

    def check(kind: str, model, source_id, name: str):
        if source_id is not None and not db.get(model, source_id):
            missing[(kind, int(source_id))] = {"kind": kind, "source_id": int(source_id), "name": name or str(source_id)}

    for row in data.get("person_options", []) + data.get("department_options", []):
        check("score_options", ScoreOption, row.get("source_score_option_id"), row.get("name", ""))
    for row in data.get("person_limits", []):
        check("positions", Position, row.get("source_target_position_id"), row.get("target_position", ""))
    for row in data.get("person_rules", []):
        check("positions", Position, row.get("source_reviewer_position_id"), row.get("reviewer_position", ""))
        check("positions", Position, row.get("source_target_position_id"), row.get("target_position", ""))
        check("users", User, row.get("source_reviewer_user_id"), row.get("reviewer_user", ""))
        for department_id, name in zip(row.get("source_target_department_ids", []), row.get("target_departments", [])):
            check("departments", Department, department_id, name)
    for row in data.get("department_rules", []):
        check("positions", Position, row.get("source_reviewer_position_id"), row.get("reviewer_position", ""))
        check("departments", Department, row.get("source_target_department_id"), row.get("target_department", ""))
    for row in data.get("department_share_rules", []):
        check("positions", Position, row.get("source_target_position_id"), row.get("target_position", ""))
    for row in data.get("manual_department_scores", []):
        check("departments", Department, row.get("source_department_id"), row.get("department", ""))
    return list(missing.values())


@router.get("/evaluations/{evaluation_id}/copy-preview")
def copy_evaluation_preview(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    source = require_evaluation(db, evaluation_id, user)
    missing = archived_copy_missing(db, source.id) if source.archived else []
    allowed = manageable_department_ids(db, user)
    department_candidates = department_choice_rows(db)
    if allowed is not None:
        department_candidates = [row for row in department_candidates if row["id"] in allowed]
    user_stmt = select(User).where(User.role == "user", User.is_active.is_(True))
    if allowed is not None:
        user_stmt = user_stmt.where(User.department_id.in_(allowed))
    candidates = {
        "positions": [{"value": row["id"], "label": row["name"]} for row in position_rows(db)],
        "departments": [{"value": row["id"], "label": row["display_name"].strip()} for row in department_candidates],
        "score_options": [{"value": row.id, "label": f"{row.name}（{row.value:g}）"} for row in db.scalars(select(ScoreOption).order_by(ScoreOption.id)).all()],
        "users": [{"value": row.id, "label": f"{row.full_name}（{row.department.name if row.department else '未分配部门'}）"} for row in db.scalars(user_stmt.order_by(User.full_name)).all()],
    }
    return {"missing": missing, "candidates": candidates}


@router.post("/evaluations/{evaluation_id}/copy")
def copy_evaluation(evaluation_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    source = require_evaluation(db, evaluation_id, user)
    year = int(payload["year"])
    sequence = next_evaluation_sequence(db, year, source.scope_key)
    target = Evaluation(
        year=year,
        sequence=sequence,
        name=(payload.get("name") or "").strip() or f"{year}-{sequence:02d}",
        scope_key=source.scope_key,
        owner_department_id=source.owner_department_id,
        owner_department_name_snapshot=source.owner_department_name_snapshot,
        created_by_id=user.id,
    )
    db.add(target)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="批次号已被其他操作占用，请重新复制。",
        ) from exc
    if source.archived:
        data = archived_snapshots(db, source.id)
        copied_count = 0
        skipped: list[str] = []

        def exists(model, source_id) -> bool:
            return source_id is not None and db.get(model, source_id) is not None

        seen: set[int] = set()
        for index, row in enumerate(data.get("person_options", [])):
            option_id = row.get("source_score_option_id")
            if not exists(ScoreOption, option_id):
                skipped.append(f"人员评分项“{row.get('name', '未知')}”")
                continue
            if option_id not in seen:
                db.add(EvaluationScoreOption(evaluation_id=target.id, score_option_id=option_id, sort_order=index))
                seen.add(option_id)
                copied_count += 1
        for row in data.get("person_limits", []):
            position_id, option_id = row.get("source_target_position_id"), row.get("source_score_option_id")
            if not exists(Position, position_id) or not exists(ScoreOption, option_id):
                skipped.append(f"人员评分限制“{row.get('target_position', '')}/{row.get('option', '')}”")
                continue
            db.add(EvaluationPersonPositionOptionLimit(evaluation_id=target.id, target_position_id=position_id, score_option_id=option_id, max_people=row.get("max_people")))
            copied_count += 1
        seen.clear()
        for index, row in enumerate(data.get("department_options", [])):
            option_id = row.get("source_score_option_id")
            if not exists(ScoreOption, option_id):
                skipped.append(f"部门评分项“{row.get('name', '未知')}”")
                continue
            if option_id not in seen:
                db.add(EvaluationDepartmentScoreOption(evaluation_id=target.id, score_option_id=option_id, sort_order=index))
                seen.add(option_id)
                copied_count += 1
        for row in data.get("department_limits", []):
            option_id = row.get("source_score_option_id")
            if not exists(ScoreOption, option_id):
                skipped.append(f"部门评分限制“{row.get('option', '未知')}”")
                continue
            db.add(EvaluationDepartmentOptionLimit(evaluation_id=target.id, score_option_id=option_id, max_count=row.get("max_count")))
            copied_count += 1
        for row in data.get("person_rules", []):
            reviewer_position_id = row.get("source_reviewer_position_id")
            target_position_id = row.get("source_target_position_id")
            reviewer_user_id = row.get("source_reviewer_user_id")
            label = f"{row.get('reviewer_position', '')}评价{row.get('target_position', '')}"
            if not exists(Position, reviewer_position_id) or not exists(Position, target_position_id):
                skipped.append(f"人员考核规则“{label}”")
                continue
            if reviewer_user_id and not exists(User, reviewer_user_id):
                skipped.append(f"人员考核规则“{label}”（指定评价人已删除）")
                continue
            source_department_ids = row.get("source_target_department_ids", [])
            valid_department_ids = [department_id for department_id in source_department_ids if exists(Department, department_id)]
            missing_department_count = len(source_department_ids) - len(valid_department_ids)
            if row.get("scope_type") != "same_department" and source_department_ids and not valid_department_ids:
                skipped.append(f"人员考核规则“{label}”（被评部门已全部删除）")
                continue
            copied = EvaluationPersonRule(evaluation_id=target.id, reviewer_position_id=reviewer_position_id, reviewer_user_id=reviewer_user_id, target_position_id=target_position_id, score_group=row.get("score_group", ""), scope_type=row.get("scope_type", "selected_departments"), weight=row.get("weight", 0))
            db.add(copied)
            db.flush()
            for department_id in valid_department_ids:
                db.add(EvaluationPersonRuleDepartment(rule_id=copied.id, department_id=department_id))
            copied_count += 1
            skipped.extend([f"规则“{label}”中的已删除部门"] * missing_department_count)
        for row in data.get("department_rules", []):
            position_id, department_id = row.get("source_reviewer_position_id"), row.get("source_target_department_id")
            if not exists(Position, position_id) or not exists(Department, department_id):
                skipped.append(f"部门考核规则“{row.get('reviewer_position', '')}评价{row.get('target_department', '')}”")
                continue
            db.add(EvaluationDepartmentRule(evaluation_id=target.id, group_key=row.get("group_key") or str(uuid4()), reviewer_position_id=position_id, target_department_id=department_id, weight=row.get("weight", 0)))
            copied_count += 1
        for row in data.get("department_share_rules", []):
            position_id = row.get("source_target_position_id")
            if not exists(Position, position_id):
                skipped.append(f"部门得分占比“{row.get('target_position', '未知')}”")
                continue
            db.add(EvaluationDepartmentScoreShareRule(evaluation_id=target.id, target_position_id=position_id, weight=row.get("weight", 0)))
            copied_count += 1
        for row in data.get("manual_department_scores", []):
            department_id = row.get("source_department_id")
            if not exists(Department, department_id):
                skipped.append(f"手动部门得分“{row.get('department', '未知')}”")
                continue
            db.add(EvaluationDepartmentManualScore(evaluation_id=target.id, department_id=department_id, score=row.get("score", 0)))
            copied_count += 1
        skipped_count = len(skipped)
        result_message = f"考核已复制，共复制 {copied_count}条配置，跳过 {skipped_count}条失效配置。"
        add_audit_log(db, target.id, user, "复制归档考核", f"来源考核ID：{source.id}；{result_message}")
        db.commit()
        return {"evaluation": evaluation_row(db, target), "message": result_message, "copied_count": copied_count, "skipped_count": skipped_count, "skipped": skipped}
    for index, option in enumerate(evaluation_person_options(db, source.id)):
        db.add(EvaluationScoreOption(evaluation_id=target.id, score_option_id=option.id, sort_order=index))
    for limit in db.scalars(select(EvaluationPersonPositionOptionLimit).where(EvaluationPersonPositionOptionLimit.evaluation_id == source.id)).all():
        db.add(EvaluationPersonPositionOptionLimit(evaluation_id=target.id, target_position_id=limit.target_position_id, score_option_id=limit.score_option_id, max_people=limit.max_people))
    for index, option in enumerate(evaluation_department_options(db, source.id)):
        db.add(EvaluationDepartmentScoreOption(evaluation_id=target.id, score_option_id=option.id, sort_order=index))
    for limit in db.scalars(select(EvaluationDepartmentOptionLimit).where(EvaluationDepartmentOptionLimit.evaluation_id == source.id)).all():
        db.add(EvaluationDepartmentOptionLimit(evaluation_id=target.id, score_option_id=limit.score_option_id, max_count=limit.max_count))
    for rule in db.scalars(select(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == source.id)).all():
        copied = EvaluationPersonRule(evaluation_id=target.id, reviewer_position_id=rule.reviewer_position_id, reviewer_user_id=rule.reviewer_user_id, target_position_id=rule.target_position_id, score_group=rule.score_group, scope_type=rule.scope_type, weight=rule.weight)
        db.add(copied)
        db.flush()
        for department in rule.target_departments:
            db.add(EvaluationPersonRuleDepartment(rule_id=copied.id, department_id=department.department_id))
    copied_department_groups: dict[str, str] = {}
    for rule in db.scalars(select(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == source.id)).all():
        copied_group_key = copied_department_groups.setdefault(rule.group_key, str(uuid4()))
        db.add(EvaluationDepartmentRule(evaluation_id=target.id, group_key=copied_group_key, reviewer_position_id=rule.reviewer_position_id, target_department_id=rule.target_department_id, weight=rule.weight))
    for rule in db.scalars(select(EvaluationDepartmentScoreShareRule).where(EvaluationDepartmentScoreShareRule.evaluation_id == source.id)).all():
        db.add(EvaluationDepartmentScoreShareRule(evaluation_id=target.id, target_position_id=rule.target_position_id, weight=rule.weight))
    for item in db.scalars(select(EvaluationDepartmentManualScore).where(EvaluationDepartmentManualScore.evaluation_id == source.id)).all():
        db.add(EvaluationDepartmentManualScore(evaluation_id=target.id, department_id=item.department_id, score=item.score))
    add_audit_log(db, target.id, user, "复制考核", f"来源考核ID：{source.id}")
    db.commit()
    copied_count = sum(
        db.scalar(select(func.count(model.id)).where(model.evaluation_id == target.id)) or 0
        for model in (
            EvaluationScoreOption, EvaluationPersonPositionOptionLimit,
            EvaluationDepartmentScoreOption, EvaluationDepartmentOptionLimit,
            EvaluationPersonRule, EvaluationDepartmentRule,
            EvaluationDepartmentScoreShareRule, EvaluationDepartmentManualScore,
        )
    )
    result_message = f"考核已复制，共复制 {copied_count}条配置，跳过 0条失效配置。"
    return {"evaluation": evaluation_row(db, target), "message": result_message, "copied_count": copied_count, "skipped_count": 0, "skipped": []}


@router.delete("/evaluations/{evaluation_id}", response_model=MessageResponse)
def delete_evaluation(evaluation_id: int, admin_password: str = "", db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    if evaluation.archived and not admin_password:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="删除已归档考核前请输入当前管理员密码。")
    if evaluation.archived and not verify_password(admin_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="管理员密码错误，请重新输入。")
    for model in (
        EvaluationVote, EvaluationReviewReopen, EvaluationTask, EvaluationScoreOption,
        EvaluationDepartmentScoreOption, EvaluationPersonPositionOptionLimit,
        EvaluationDepartmentOptionLimit, EvaluationDepartmentScoreShareRule,
        EvaluationDepartmentManualScore, ArchivedPersonScore, ArchivedDepartmentScore,
        ArchivedVoteDetail, ArchivedRuleSnapshot, ArchivedSubmission, EvaluationAuditLog,
    ):
        db.execute(delete(model).where(model.evaluation_id == evaluation_id))
    person_rule_ids = db.scalars(select(EvaluationPersonRule.id).where(EvaluationPersonRule.evaluation_id == evaluation_id)).all()
    if person_rule_ids:
        db.execute(delete(EvaluationPersonRuleDepartment).where(EvaluationPersonRuleDepartment.rule_id.in_(person_rule_ids)))
    db.execute(delete(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == evaluation_id))
    db.execute(delete(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == evaluation_id))
    db.delete(evaluation)
    db.commit()
    return MessageResponse(message="考核已删除。")


@router.post("/evaluations/{evaluation_id}/generate-tasks", response_model=EvaluationActionResponse)
def generate_evaluation_tasks(evaluation_id: int, confirm: bool = False, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation_for_update(db, evaluation_id, user)
    if evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已归档考核不能生成任务。")
    existing_tasks = db.scalar(select(func.count(EvaluationTask.id)).where(EvaluationTask.evaluation_id == evaluation_id)) or 0
    if existing_tasks and not confirm:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="重新生成任务会覆盖现有任务和评分，请确认后重试。")
    count = generate_tasks(db, evaluation)
    add_audit_log(db, evaluation_id, user, "生成考核任务", f"生成任务数：{count}；覆盖前任务数：{existing_tasks}")
    db.commit()
    return EvaluationActionResponse(message=f"已生成 {count} 个考核任务。", evaluation=evaluation_row(db, evaluation))


@router.post("/evaluations/{evaluation_id}/clear-tasks", response_model=EvaluationActionResponse)
def clear_evaluation_tasks(evaluation_id: int, confirm: bool = False, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation_for_update(db, evaluation_id, user)
    if evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已归档考核不能清空任务。")
    if not confirm:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="清空任务会同时删除已提交评分，请确认后重试。")
    task_count = db.scalar(select(func.count(EvaluationTask.id)).where(EvaluationTask.evaluation_id == evaluation_id)) or 0
    vote_count = db.scalar(select(func.count(EvaluationVote.id)).where(EvaluationVote.evaluation_id == evaluation_id)) or 0
    db.execute(delete(EvaluationVote).where(EvaluationVote.evaluation_id == evaluation_id))
    db.execute(delete(EvaluationReviewReopen).where(EvaluationReviewReopen.evaluation_id == evaluation_id))
    db.execute(delete(EvaluationTask).where(EvaluationTask.evaluation_id == evaluation_id))
    evaluation.tasks_generated = False
    evaluation.is_open = False
    evaluation.open_slot = None
    add_audit_log(db, evaluation_id, user, "清空考核任务", f"删除任务：{task_count} 个；删除评分：{vote_count} 条")
    db.commit()
    return EvaluationActionResponse(message=f"已清空 {task_count} 个考核任务。", evaluation=evaluation_row(db, evaluation))


@router.post("/evaluations/{evaluation_id}/toggle-open", response_model=EvaluationActionResponse)
def toggle_evaluation(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation_for_update(db, evaluation_id, user)
    if evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已归档考核不能修改状态。")
    opening = not evaluation.is_open
    overlap_count = 0
    if opening:
        active = db.scalar(
            select(Evaluation)
            .where(
                Evaluation.is_open.is_(True),
                Evaluation.scope_key == evaluation.scope_key,
                Evaluation.id != evaluation.id,
            )
            .order_by(Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.id.desc())
            .with_for_update()
        )
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"“{active.name}”正在开放，请先关闭该考核。",
            )
        reviewer_ids = select(EvaluationTask.reviewer_id).where(
            EvaluationTask.evaluation_id == evaluation.id,
        ).distinct()
        overlap_count = db.scalar(
            select(func.count(func.distinct(EvaluationTask.reviewer_id)))
            .join(Evaluation, Evaluation.id == EvaluationTask.evaluation_id)
            .where(
                Evaluation.is_open.is_(True),
                Evaluation.id != evaluation.id,
                EvaluationTask.reviewer_id.in_(reviewer_ids),
            )
        ) or 0
    evaluation.is_open = not evaluation.is_open
    evaluation.open_slot = 1 if evaluation.is_open else None
    add_audit_log(db, evaluation_id, user, "更新考核状态", "开放考核" if evaluation.is_open else "关闭考核")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        active = db.scalar(
            select(Evaluation)
            .where(
                Evaluation.is_open.is_(True),
                Evaluation.scope_key == evaluation.scope_key,
                Evaluation.id != evaluation_id,
            )
            .order_by(Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.id.desc())
        )
        detail = f"“{active.name}”正在开放，请先关闭该考核。" if active else "已有其他考核正在开放。"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
    message = "考核状态已更新。"
    if opening and overlap_count:
        message = f"考核已开放；有 {overlap_count} 名评价人同时参与其他开放考核，请留意任务区分。"
    return EvaluationActionResponse(message=message, evaluation=evaluation_row(db, evaluation))


@router.post("/evaluations/{evaluation_id}/archive", response_model=EvaluationActionResponse)
def archive(evaluation_id: int, confirm: bool = False, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation_for_update(db, evaluation_id, user)
    if not confirm:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="归档会固化当前分数和规则快照，请确认后重试。")
    progress = evaluation_task_progress(db, evaluation_id)
    if not progress["complete"]:
        reopen_hint = f"；待重新提交 {progress['pending_reopens']} 人" if progress["pending_reopens"] else ""
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"所有考核任务完成后才能归档。当前完成 {progress['submitted_tasks']} / {progress['total_tasks']}{reopen_hint}。",
        )
    try:
        archive_evaluation(db, evaluation)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    add_audit_log(db, evaluation_id, user, "归档考核", f"任务完成：{progress['submitted_tasks']} / {progress['total_tasks']}")
    db.commit()
    return EvaluationActionResponse(message="归档统计已完成。", evaluation=evaluation_row(db, evaluation))


@router.get("/evaluations/{evaluation_id}/live-stats")
def live_stats(evaluation_id: int, q: str = "", people_page: int = 1, details_page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    result = calculate_evaluation_scores(db, evaluation)
    people = result["people"]
    departments = result["departments"]
    details = list(reversed(result["details"]))
    if q:
        keyword = q.strip()
        people = [
            item for item in people
            if keyword in item["full_name"] or keyword in item["department_name"] or keyword in item["position_name"]
        ]
        departments = [item for item in departments if keyword in item["department_name"]]
        details = [
            item for item in details
            if keyword in item["reviewer_name"] or keyword in item["target_name"] or keyword in item["rule_label"]
        ]
    people_page_info = pagination(len(people), people_page, 10)
    details_page_info = pagination(len(details), details_page, 20)
    return {
        "evaluation": evaluation_row(db, evaluation),
        "people": people[(people_page_info.page - 1) * 10:people_page_info.page * 10],
        "people_pagination": people_page_info,
        "departments": departments,
        "details": details[(details_page_info.page - 1) * 20:details_page_info.page * 20],
        "details_pagination": details_page_info,
        "stats": {
            "total_tasks": result["total_tasks"],
            "submitted_tasks": result["submitted_tasks"],
        },
    }


@router.get("/evaluations/{evaluation_id}/review-submissions")
def review_submissions(evaluation_id: int, q: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    allowed = manageable_department_ids(db, user)
    if evaluation.archived:
        stmt = select(ArchivedSubmission).where(ArchivedSubmission.evaluation_id == evaluation_id)
        if allowed is not None:
            stmt = stmt.where(ArchivedSubmission.reviewer_department_id.in_(allowed))
        if q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(ArchivedSubmission.reviewer_name.like(like), ArchivedSubmission.department_name.like(like), ArchivedSubmission.position_name.like(like)))
        rows = db.scalars(stmt.order_by(ArchivedSubmission.reviewer_name)).all()
        page_info = pagination(len(rows), page, 10)
        return {
            "evaluation": evaluation_row(db, evaluation),
            "items": [{
                "reviewer_id": row.reviewer_id, "reviewer_name": row.reviewer_name,
                "department_name": row.department_name, "position_name": row.position_name,
                "task_count": row.task_count, "submitted_count": row.submitted_count,
                "status_label": row.status_label, "reopened": False, "can_reopen": False, "can_cancel": False,
            } for row in rows[(page_info.page - 1) * page_info.page_size:page_info.page * page_info.page_size]],
            "pagination": page_info,
        }
    task_stmt = (
        select(EvaluationTask)
        .join(User, User.id == EvaluationTask.reviewer_id)
        .where(EvaluationTask.evaluation_id == evaluation_id)
    )
    if allowed is not None:
        task_stmt = task_stmt.where(User.department_id.in_(allowed))
    tasks = db.scalars(task_stmt.order_by(EvaluationTask.reviewer_id, EvaluationTask.id)).all()
    votes_by_reviewer = {
        reviewer_id: count
        for reviewer_id, count in db.execute(
            select(EvaluationVote.reviewer_id, func.count(EvaluationVote.id))
            .where(EvaluationVote.evaluation_id == evaluation_id)
            .group_by(EvaluationVote.reviewer_id)
        ).all()
    }
    reopen_by_reviewer = {
        item.reviewer_id: item
        for item in db.scalars(select(EvaluationReviewReopen).where(EvaluationReviewReopen.evaluation_id == evaluation_id)).all()
    }
    tasks_by_reviewer: dict[int, list[EvaluationTask]] = {}
    for task in tasks:
        tasks_by_reviewer.setdefault(task.reviewer_id, []).append(task)
    rows = []
    for reviewer_id, reviewer_tasks in tasks_by_reviewer.items():
        reviewer = reviewer_tasks[0].reviewer
        submitted_count = votes_by_reviewer.get(reviewer_id, 0)
        reopened = reopen_by_reviewer.get(reviewer_id)
        if reopened:
            status_label = "已退回可修改"
        elif submitted_count >= len(reviewer_tasks) and reviewer_tasks:
            status_label = "已提交"
        elif submitted_count:
            status_label = "部分提交"
        else:
            status_label = "未提交"
        department_name = reviewer.department.name if reviewer.department else ""
        position_name = reviewer.position.name if reviewer.position else ""
        if q and q.strip() not in reviewer.full_name and q.strip() not in department_name and q.strip() not in position_name:
            continue
        rows.append({
            "reviewer_id": reviewer.id,
            "reviewer_name": reviewer.full_name,
            "department_name": department_name,
            "position_name": position_name,
            "task_count": len(reviewer_tasks),
            "submitted_count": submitted_count,
            "status_label": status_label,
            "reopened": bool(reopened),
            "can_reopen": evaluation.is_open and not evaluation.archived and submitted_count >= len(reviewer_tasks) and not reopened,
            "can_cancel": evaluation.is_open and not evaluation.archived and reopened is not None,
        })
    page_info = pagination(len(rows), page, 10)
    return {
        "evaluation": evaluation_row(db, evaluation),
        "items": rows[(page_info.page - 1) * page_info.page_size:page_info.page * page_info.page_size],
        "pagination": page_info,
    }


@router.post("/evaluations/{evaluation_id}/review-submissions/{reviewer_id}/details")
def review_submission_details(
    evaluation_id: int,
    reviewer_id: int,
    payload: ScoreDetailPasswordRequest,
    page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_admin),
):
    evaluation = require_evaluation(db, evaluation_id, user)
    if evaluation.archived:
        submission = db.scalar(select(ArchivedSubmission).where(
            ArchivedSubmission.evaluation_id == evaluation_id,
            ArchivedSubmission.reviewer_id == reviewer_id,
        ))
        if not submission:
            raise HTTPException(status_code=404, detail="该用户在本次考核中没有评分任务。")
        ensure_department_manageable(db, user, submission.reviewer_department_id)
        password_hash = score_detail_password_hash()
        if not password_hash:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="未配置评分详情查看密码。")
        if not verify_password(payload.password, password_hash):
            add_audit_log(db, evaluation_id, user, "评分详情验证失败", f"被查看评分人：{submission.reviewer_name}")
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="查看密码错误。")
        details = db.scalars(select(ArchivedVoteDetail).where(
            ArchivedVoteDetail.evaluation_id == evaluation_id,
            ArchivedVoteDetail.reviewer_id == reviewer_id,
        ).order_by(ArchivedVoteDetail.id.desc())).all()
        page_info = pagination(len(details), page, 10)
        add_audit_log(db, evaluation_id, user, "查看归档评分详情", f"评分人：{submission.reviewer_name}")
        db.commit()
        return {
            "reviewer": {"id": reviewer_id, "full_name": submission.reviewer_name, "department_name": submission.department_name, "position_name": submission.position_name},
            "items": [{"id": item.id, "target_name": item.target_name, "task_type": item.task_type, "option_name": item.option_name, "score_value": item.score_value, "weight": item.weight, "weighted_score": item.weighted_score, "created_at": item.created_at} for item in details[(page_info.page - 1) * page_info.page_size:page_info.page * page_info.page_size]],
            "pagination": page_info,
        }
    reviewer = db.get(User, reviewer_id)
    if not reviewer:
        raise HTTPException(status_code=404, detail="评分人不存在。")
    ensure_department_manageable(db, user, reviewer.department_id)
    password_hash = score_detail_password_hash()
    if not password_hash:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="未配置评分详情查看密码。")
    if not verify_password(payload.password, password_hash):
        add_audit_log(db, evaluation_id, user, "评分详情验证失败", f"被查看评分人：{reviewer.full_name}")
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="查看密码错误。")
    task_count = db.scalar(select(func.count(EvaluationTask.id)).where(
        EvaluationTask.evaluation_id == evaluation_id,
        EvaluationTask.reviewer_id == reviewer_id,
    )) or 0
    if not task_count:
        raise HTTPException(status_code=404, detail="该用户在本次考核中没有评分任务。")

    votes = db.scalars(
        select(EvaluationVote)
        .where(EvaluationVote.evaluation_id == evaluation_id, EvaluationVote.reviewer_id == reviewer_id)
        .order_by(EvaluationVote.created_at.desc(), EvaluationVote.id.desc())
    ).all()
    rows = []
    for vote in votes:
        task = vote.task
        target_name = ""
        if task.task_type == "person" and task.target_user:
            target_name = task.target_user.full_name
        elif task.task_type == "department" and task.target_department:
            target_name = task.target_department.name
        rows.append({
            "id": vote.id,
            "target_name": target_name,
            "task_type": task.task_type,
            "option_name": vote.option.name,
            "score_value": vote.score_value,
            "weight": task.weight,
            "weighted_score": vote.score_value * task.weight,
            "created_at": vote.created_at,
        })
    page_info = pagination(len(rows), page, 10)
    add_audit_log(
        db,
        evaluation_id,
        user,
        "查看评分详情",
        f"考核：{evaluation.name}；评分人：{reviewer.full_name}；第 {page_info.page} 页",
    )
    db.commit()
    return {
        "reviewer": {
            "id": reviewer.id,
            "full_name": reviewer.full_name,
            "department_name": reviewer.department.name if reviewer.department else "",
            "position_name": reviewer.position.name if reviewer.position else "",
        },
        "items": rows[(page_info.page - 1) * page_info.page_size:page_info.page * page_info.page_size],
        "pagination": page_info,
    }


@router.post("/evaluations/{evaluation_id}/review-submissions/{reviewer_id}/reopen", response_model=MessageResponse)
def reopen_review_submission(evaluation_id: int, reviewer_id: int, payload: dict | None = None, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation_for_update(db, evaluation_id, user)
    reviewer = db.get(User, reviewer_id)
    if not reviewer:
        raise HTTPException(status_code=404, detail="评分人不存在。")
    ensure_department_manageable(db, user, reviewer.department_id)
    if not evaluation.is_open or evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有考核开放且未归档时，才能允许用户重新修改评分。")
    task_count = db.scalar(select(func.count(EvaluationTask.id)).where(EvaluationTask.evaluation_id == evaluation_id, EvaluationTask.reviewer_id == reviewer_id)) or 0
    vote_count = db.scalar(select(func.count(EvaluationVote.id)).where(EvaluationVote.evaluation_id == evaluation_id, EvaluationVote.reviewer_id == reviewer_id)) or 0
    if not task_count or vote_count < task_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户尚未完整提交评分，不能退回修改。")
    reason = (payload or {}).get("reason", "")
    existing = db.scalar(select(EvaluationReviewReopen).where(EvaluationReviewReopen.evaluation_id == evaluation_id, EvaluationReviewReopen.reviewer_id == reviewer_id))
    if existing:
        existing.reason = reason
        existing.created_by = user.id
    else:
        db.add(EvaluationReviewReopen(evaluation_id=evaluation_id, reviewer_id=reviewer_id, created_by=user.id, reason=reason))
    add_audit_log(db, evaluation_id, user, "允许重新修改评分", f"评分人：{reviewer.full_name}")
    db.commit()
    return MessageResponse(message=f"已允许 {reviewer.full_name} 重新修改评分。")


@router.post("/evaluations/{evaluation_id}/review-submissions/{reviewer_id}/cancel", response_model=MessageResponse)
def cancel_review_submission(evaluation_id: int, reviewer_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation_for_update(db, evaluation_id, user)
    reviewer = db.get(User, reviewer_id)
    if not reviewer:
        raise HTTPException(status_code=404, detail="评分人不存在。")
    ensure_department_manageable(db, user, reviewer.department_id)
    if not evaluation.is_open or evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有考核开放且未归档时，才能取消重新修改权限。")
    db.execute(delete(EvaluationReviewReopen).where(EvaluationReviewReopen.evaluation_id == evaluation_id, EvaluationReviewReopen.reviewer_id == reviewer_id))
    add_audit_log(db, evaluation_id, user, "取消重新修改评分", f"评分人ID：{reviewer_id}")
    db.commit()
    return MessageResponse(message="已取消重新修改权限。")


@router.get("/evaluations/{evaluation_id}/details")
def evaluation_details(evaluation_id: int, q: str = "", people_page: int = 1, details_page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    people_stmt = select(ArchivedPersonScore).where(ArchivedPersonScore.evaluation_id == evaluation_id)
    departments_stmt = select(ArchivedDepartmentScore).where(ArchivedDepartmentScore.evaluation_id == evaluation_id)
    details_stmt = select(ArchivedVoteDetail).where(ArchivedVoteDetail.evaluation_id == evaluation_id)
    if q:
        like = f"%{q}%"
        people_stmt = people_stmt.where(ArchivedPersonScore.full_name.like(like) | ArchivedPersonScore.department_name.like(like) | ArchivedPersonScore.position_name.like(like))
        departments_stmt = departments_stmt.where(ArchivedDepartmentScore.department_name.like(like))
        details_stmt = details_stmt.where(or_(ArchivedVoteDetail.reviewer_name.like(like), ArchivedVoteDetail.target_name.like(like), ArchivedVoteDetail.option_name.like(like), ArchivedVoteDetail.rule_label.like(like)))
    people_total = db.scalar(select(func.count()).select_from(people_stmt.order_by(None).subquery())) or 0
    details_total = db.scalar(select(func.count()).select_from(details_stmt.order_by(None).subquery())) or 0
    people_page_info = pagination(people_total, people_page, 10)
    details_page_info = pagination(details_total, details_page, 20)
    snapshots = db.scalars(select(ArchivedRuleSnapshot).where(ArchivedRuleSnapshot.evaluation_id == evaluation_id).order_by(ArchivedRuleSnapshot.id)).all()
    return {
        "evaluation": evaluation_row(db, evaluation),
        "people": [
            {"id": item.id, "full_name": item.full_name, "department_name": item.department_name, "position_name": item.position_name, "final_score": item.final_score}
            for item in db.scalars(people_stmt.order_by(ArchivedPersonScore.final_score.desc()).offset((people_page_info.page - 1) * people_page_info.page_size).limit(people_page_info.page_size)).all()
        ],
        "people_pagination": people_page_info,
        "departments": [
            {"id": item.id, "department_name": item.department_name, "final_score": item.final_score}
            for item in db.scalars(departments_stmt.order_by(ArchivedDepartmentScore.final_score.desc())).all()
        ],
        "details": [
            {"id": item.id, "reviewer_name": item.reviewer_name, "target_name": item.target_name, "task_type": item.task_type, "option_name": item.option_name, "score_value": item.score_value, "weight": item.weight, "weighted_score": item.weighted_score, "rule_label": item.rule_label}
            for item in db.scalars(details_stmt.order_by(ArchivedVoteDetail.id.desc()).offset((details_page_info.page - 1) * details_page_info.page_size).limit(details_page_info.page_size)).all()
        ],
        "details_pagination": details_page_info,
        "snapshots": [{"id": item.id, "snapshot_type": item.snapshot_type, "title": item.title, "payload": snapshot_payload(item.payload)} for item in snapshots],
    }


@router.get("/evaluations/{evaluation_id}/exports/person-scores")
def export_person_scores(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    if not evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能导出已归档考核的人员得分。")
    scores = db.scalars(
        select(ArchivedPersonScore)
        .where(ArchivedPersonScore.evaluation_id == evaluation_id)
        .order_by(ArchivedPersonScore.final_score.desc(), ArchivedPersonScore.full_name)
    ).all()
    rows = [[item.full_name, item.department_name, round(item.final_score, 2)] for item in scores]
    return excel_response(score_workbook("人员得分", ["姓名", "所在部门", "得分"], rows), f"{evaluation.name}-人员得分.xlsx")


@router.get("/evaluations/{evaluation_id}/exports/department-scores")
def export_department_scores(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    evaluation = require_evaluation(db, evaluation_id, user)
    if not evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只能导出已归档考核的部门得分。")
    scores = db.scalars(
        select(ArchivedDepartmentScore)
        .where(ArchivedDepartmentScore.evaluation_id == evaluation_id)
        .order_by(ArchivedDepartmentScore.final_score.desc(), ArchivedDepartmentScore.department_name)
    ).all()
    rows = [[item.department_name, round(item.final_score, 2)] for item in scores]
    return excel_response(score_workbook("部门得分", ["部门名称", "得分"], rows), f"{evaluation.name}-部门得分.xlsx")


def require_app_user(user: User) -> None:
    if user.role == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员无需参与评分。")


def app_workspace_payload(db: Session, user: User, evaluation: Evaluation) -> dict:
    tasks = db.scalars(
        select(EvaluationTask)
        .where(EvaluationTask.evaluation_id == evaluation.id, EvaluationTask.reviewer_id == user.id)
        .order_by(EvaluationTask.task_type.desc(), EvaluationTask.id)
    ).all()
    submitted = bool(db.scalar(select(EvaluationTask.submitted).where(EvaluationTask.evaluation_id == evaluation.id, EvaluationTask.reviewer_id == user.id, EvaluationTask.submitted.is_(True))))
    reopened = bool(db.scalar(
        select(EvaluationReviewReopen).where(
            EvaluationReviewReopen.evaluation_id == evaluation.id,
            EvaluationReviewReopen.reviewer_id == user.id,
        )
    ))
    current_choices = {
        vote.task_id: vote.score_option_id
        for vote in db.scalars(
            select(EvaluationVote).where(
                EvaluationVote.evaluation_id == evaluation.id,
                EvaluationVote.reviewer_id == user.id,
            )
        ).all()
    }
    return {
        "evaluation": evaluation_row(db, evaluation),
        "task_groups": task_groups(db, tasks),
        "submitted": submitted and not reopened,
        "reopened": reopened,
        "current_choices": current_choices,
        "limit_map": task_limit_map(db, evaluation.id),
    }


@router.get("/app/evaluations")
def app_evaluations(db: Session = Depends(get_db), user: User = Depends(require_api_user)):
    require_app_user(user)
    live_rows = db.execute(
        select(Evaluation, func.count(EvaluationTask.id).label("task_count"), func.sum(EvaluationTask.submitted.cast(Integer)).label("submitted_count"))
        .join(EvaluationTask, EvaluationTask.evaluation_id == Evaluation.id)
        .where(EvaluationTask.reviewer_id == user.id, Evaluation.archived.is_(False))
        .group_by(Evaluation.id)
        .order_by(Evaluation.is_open.desc(), Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.id.desc())
    ).all()
    items = []
    for evaluation, task_count, submitted_count in live_rows:
        reopened = bool(db.scalar(select(EvaluationReviewReopen.id).where(
            EvaluationReviewReopen.evaluation_id == evaluation.id,
            EvaluationReviewReopen.reviewer_id == user.id,
        )))
        submitted_count = int(submitted_count or 0)
        task_count = int(task_count or 0)
        submitted = task_count > 0 and submitted_count >= task_count and not reopened
        items.append({
            "id": evaluation.id,
            "name": evaluation.name,
            "year": evaluation.year,
            "sequence": evaluation.sequence,
            "owner_department_name": evaluation.owner_department_name_snapshot or "全局",
            "is_open": evaluation.is_open,
            "archived": False,
            "task_count": task_count,
            "completed_count": submitted_count,
            "submitted": submitted,
            "status": "submitted" if submitted else "pending",
            "created_at": evaluation.created_at,
        })

    archived_rows = db.execute(
        select(ArchivedSubmission, Evaluation)
        .join(Evaluation, Evaluation.id == ArchivedSubmission.evaluation_id)
        .where(ArchivedSubmission.reviewer_identity_key == user.identity_key)
        .order_by(Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.id.desc())
    ).all()
    for submission, evaluation in archived_rows:
        items.append({
            "id": evaluation.id,
            "name": evaluation.name,
            "year": evaluation.year,
            "sequence": evaluation.sequence,
            "owner_department_name": evaluation.owner_department_name_snapshot or "全局",
            "is_open": False,
            "archived": True,
            "task_count": submission.task_count,
            "completed_count": submission.submitted_count,
            "submitted": True,
            "status": "history",
            "submitted_at": submission.submitted_at,
            "created_at": evaluation.created_at,
        })
    return {"items": items}


@router.get("/app/evaluations/{evaluation_id}")
def app_evaluation_workspace(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_user)):
    require_app_user(user)
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation or evaluation.archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核不存在或已归档。")
    task_exists = db.scalar(select(EvaluationTask.id).where(
        EvaluationTask.evaluation_id == evaluation_id,
        EvaluationTask.reviewer_id == user.id,
    ))
    if not task_exists:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有该考核的评分任务。")
    return app_workspace_payload(db, user, evaluation)


@router.post("/app/evaluations/{evaluation_id}/submit", response_model=MessageResponse)
def submit_app_evaluation(evaluation_id: int, payload: VoteSubmitRequest, db: Session = Depends(get_db), user: User = Depends(require_api_user)):
    require_app_user(user)
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation or not evaluation.is_open or evaluation.archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该考核当前未开放。")
    try:
        submit_votes(db, evaluation, user, payload.choices)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MessageResponse(message="评分已提交。")


@router.get("/app/evaluations/{evaluation_id}/submission")
def app_submission(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_user)):
    require_app_user(user)
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核不存在。")
    if evaluation.archived:
        submission = db.scalar(select(ArchivedSubmission).where(
            ArchivedSubmission.evaluation_id == evaluation_id,
            ArchivedSubmission.reviewer_identity_key == user.identity_key,
        ))
        if not submission:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有该考核的历史提交记录。")
        details = db.scalars(select(ArchivedVoteDetail).where(
            ArchivedVoteDetail.evaluation_id == evaluation_id,
            ArchivedVoteDetail.reviewer_identity_key == user.identity_key,
        ).order_by(ArchivedVoteDetail.id)).all()
        return {
            "evaluation": evaluation_row(db, evaluation),
            "submitted_at": submission.submitted_at,
            "task_count": submission.task_count,
            "items": [{"id": item.id, "target_name": item.target_name, "task_type": item.task_type, "option_name": item.option_name} for item in details],
        }
    task_count = db.scalar(select(func.count(EvaluationTask.id)).where(
        EvaluationTask.evaluation_id == evaluation_id,
        EvaluationTask.reviewer_id == user.id,
    )) or 0
    if not task_count:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有该考核的提交记录。")
    votes = db.scalars(select(EvaluationVote).where(
        EvaluationVote.evaluation_id == evaluation_id,
        EvaluationVote.reviewer_id == user.id,
    ).order_by(EvaluationVote.id)).all()
    if len(votes) < task_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该考核尚未完整提交。")
    return {
        "evaluation": evaluation_row(db, evaluation),
        "submitted_at": max((vote.created_at for vote in votes), default=None),
        "task_count": task_count,
        "items": [{
            "id": vote.id,
            "target_name": vote.task.target_user.full_name if vote.task.task_type == "person" and vote.task.target_user else vote.task.target_department.name if vote.task.target_department else "",
            "task_type": vote.task.task_type,
            "option_name": vote.option.name,
        } for vote in votes],
    }


@router.get("/app/evaluation")
def legacy_app_evaluation(db: Session = Depends(get_db), user: User = Depends(require_api_user)):
    require_app_user(user)
    evaluations = db.scalars(
        select(Evaluation)
        .join(EvaluationTask, EvaluationTask.evaluation_id == Evaluation.id)
        .where(Evaluation.is_open.is_(True), EvaluationTask.reviewer_id == user.id)
        .distinct()
        .order_by(Evaluation.year.desc(), Evaluation.sequence.desc(), Evaluation.id.desc())
    ).all()
    if not evaluations:
        return {"evaluation": None, "task_groups": [], "submitted": False, "reopened": False, "current_choices": {}, "limit_map": {}}
    if len(evaluations) > 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前有多个考核，请从“我的考核”页面选择。")
    return app_workspace_payload(db, user, evaluations[0])


@router.post("/app/evaluation/submit", response_model=MessageResponse)
def legacy_submit_evaluation(payload: VoteSubmitRequest, db: Session = Depends(get_db), user: User = Depends(require_api_user)):
    require_app_user(user)
    evaluations = db.scalars(
        select(Evaluation)
        .join(EvaluationTask, EvaluationTask.evaluation_id == Evaluation.id)
        .where(Evaluation.is_open.is_(True), EvaluationTask.reviewer_id == user.id)
        .distinct()
    ).all()
    if len(evaluations) != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请从“我的考核”页面选择要提交的考核。")
    return submit_app_evaluation(evaluations[0].id, payload, db, user)
