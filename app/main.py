import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.database import SessionLocal, get_db, init_db
from app.models import (
    ArchivedDepartmentScore,
    ArchivedPersonScore,
    ArchivedRuleSnapshot,
    ArchivedVoteDetail,
    Department,
    Evaluation,
    EvaluationAuditLog,
    EvaluationDepartmentOptionLimit,
    EvaluationDepartmentManualScore,
    EvaluationDepartmentRule,
    EvaluationDepartmentRuleOptionLimit,
    EvaluationDepartmentShareRule,
    EvaluationDepartmentScoreOption,
    EvaluationDepartmentScoreShareRule,
    EvaluationPersonPositionOptionLimit,
    EvaluationPersonRule,
    EvaluationPersonRuleDepartment,
    EvaluationPersonRuleOptionLimit,
    EvaluationReviewReopen,
    EvaluationScoreOption,
    EvaluationTask,
    EvaluationVote,
    Position,
    ScoreOption,
    User,
)
from app.security import hash_password, verify_password
from app.services import archive_evaluation, calculate_evaluation_scores, evaluation_department_options, evaluation_person_options, evaluation_task_progress, generate_tasks, submit_votes, validate_vote_payload

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="毕节金融监管分局人事考核系统")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def startup() -> None:
    init_db()


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def flash(response: RedirectResponse, message: str, category: str = "info") -> RedirectResponse:
    response.set_cookie("flash", f"{category}|{quote(message)}", httponly=True, samesite="lax")
    return response


@app.middleware("http")
async def block_archived_evaluation_edits(request: Request, call_next):
    parts = request.url.path.strip("/").split("/")
    if len(parts) >= 4 and parts[0] == "admin" and parts[1] == "evaluations" and parts[2].isdigit():
        action = parts[3]
        if action not in {"details", "live-stats", "review-submissions", "copy", "delete"}:
            db = SessionLocal()
            try:
                evaluation = db.get(Evaluation, int(parts[2]))
                if evaluation and evaluation.archived:
                    return flash(redirect("/admin/evaluations"), "已归档考核只能查看详情、复制或删除，不能再修改。", "error")
            finally:
                db.close()
    return await call_next(request)


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200) -> HTMLResponse:
    data = context or {}
    raw = request.cookies.get("flash")
    if raw and "|" in raw:
        category, message = raw.split("|", 1)
        data["flash"] = {"category": category, "message": unquote(message)}
    response = templates.TemplateResponse(request, name, data, status_code=status_code)
    if raw:
        response.delete_cookie("flash")
    response.headers["Cache-Control"] = "no-store"
    return response


def pagination(total: int, page: int, page_size: int) -> dict:
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(page, 1), total_pages)
    return {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "page_size": page_size,
    }


def paginate_items(items: list, page: int, page_size: int) -> tuple[list, dict]:
    page_info = pagination(len(items), page, page_size)
    start = (page_info["page"] - 1) * page_size
    return items[start:start + page_size], page_info


def count_select(db: Session, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


def add_audit_log(db: Session, evaluation_id: int, user: User | None, action: str, detail: str = "") -> None:
    db.add(EvaluationAuditLog(
        evaluation_id=evaluation_id,
        actor_id=user.id if user else None,
        actor_name=user.full_name if user else "",
        action=action,
        detail=detail,
    ))


def snapshot_preview(payload: str) -> str:
    try:
        value = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return payload
    if not value:
        return "无"
    if isinstance(value, list):
        return f"{len(value)} 条：" + "；".join(json.dumps(item, ensure_ascii=False) for item in value[:3])
    return json.dumps(value, ensure_ascii=False)


def next_sort_order(db: Session, model: type) -> int:
    current = db.scalar(select(func.max(model.sort_order))) or 0
    return current + 1


def normalize_sort_orders(db: Session, model: type) -> list:
    rows = db.scalars(select(model).order_by(model.sort_order, model.id)).all()
    for index, row in enumerate(rows, start=1):
        row.sort_order = index
    return rows


def reserve_sort_order(db: Session, model: type, target_order: int, current_id: int | None = None) -> int:
    rows = normalize_sort_orders(db, model)
    max_order = len(rows) if current_id is not None else len(rows) + 1
    target_order = min(max(target_order, 1), max_order)
    stmt = select(model).where(model.sort_order >= target_order)
    if current_id is not None:
        stmt = stmt.where(model.id != current_id)
    rows = db.scalars(stmt.order_by(model.sort_order.desc(), model.id.desc())).all()
    for row in rows:
        row.sort_order += 1
    return target_order


def apply_sort_order(db: Session, item, model: type, sort_order: str) -> None:
    if not sort_order:
        return
    rows = normalize_sort_orders(db, model)
    ordered = [row for row in rows if row.id != item.id]
    target_index = min(max(int(sort_order) - 1, 0), len(ordered))
    ordered.insert(target_index, item)
    for index, row in enumerate(ordered, start=1):
        row.sort_order = index


def departments_order():
    return (Department.sort_order, Department.id)


def positions_order():
    return (Position.sort_order, Position.id)


def department_rows(db: Session) -> list[dict]:
    parent = aliased(Department)
    rows = db.execute(
        select(
            Department.id,
            Department.name,
            Department.parent_id,
            Department.sort_order,
            parent.name.label("parent_name"),
        )
        .outerjoin(parent, Department.parent_id == parent.id)
        .order_by(*departments_order())
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "parent_id": row.parent_id,
            "parent_name": row.parent_name,
            "sort_order": row.sort_order,
        }
        for row in rows
    ]


def department_choice_rows(db: Session) -> list[dict]:
    rows = department_rows(db)
    by_parent: dict[int | None, list[dict]] = {}
    for row in rows:
        by_parent.setdefault(row["parent_id"], []).append(row)

    choices: list[dict] = []
    visited: set[int] = set()

    def walk(parent_id: int | None, depth: int) -> None:
        for row in by_parent.get(parent_id, []):
            if row["id"] in visited:
                continue
            visited.add(row["id"])
            item = dict(row)
            item["depth"] = depth
            item["display_name"] = f"{'　' * depth}{row['name']}"
            item["has_children"] = bool(by_parent.get(row["id"]))
            choices.append(item)
            walk(row["id"], depth + 1)

    walk(None, 0)
    for row in rows:
        if row["id"] not in visited:
            item = dict(row)
            item["depth"] = 0
            item["display_name"] = row["name"]
            item["has_children"] = bool(by_parent.get(row["id"]))
            choices.append(item)
    return choices


def position_rows(db: Session) -> list[dict]:
    rows = db.execute(select(Position.id, Position.name, Position.sort_order).order_by(*positions_order())).all()
    return [{"id": row.id, "name": row.name, "sort_order": row.sort_order} for row in rows]


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


def task_options_map(db: Session, tasks: list[EvaluationTask]) -> dict[int, list[ScoreOption]]:
    evaluation_ids = {task.evaluation_id for task in tasks}
    evaluation_id = next(iter(evaluation_ids), None)
    person_options = evaluation_person_options(db, evaluation_id) if evaluation_id else []
    department_options = evaluation_department_options(db, evaluation_id) if evaluation_id else []
    return {
        task.id: person_options if task.task_type == "person" else department_options
        for task in tasks
    }


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
            "options": person_options,
            "tasks": grouped_tasks,
        })
    if department_tasks:
        groups.append({
            "type": "department",
            "title": "部门考核",
            "limit_text": score_limit_text(db, evaluation_id, "department"),
            "options": department_options,
            "tasks": department_tasks,
        })
    return groups


def parse_limit_map(score_option_ids: list[int], limits: list[str]) -> dict[int, int | None]:
    result: dict[int, int | None] = {}
    for index, option_id in enumerate(score_option_ids):
        raw = limits[index] if index < len(limits) else ""
        result[option_id] = int(raw) if raw else None
    return result


def target_department_ids_from_form(target_department_ids: list[int], target_department_id: str = "") -> list[int]:
    ids = list(target_department_ids)
    if target_department_id:
        ids.append(int(target_department_id))
    return list(dict.fromkeys(ids))


def department_selection_summary(department_ids: list[int], labels: dict[int, str], order: dict[int, int]) -> tuple[str, str]:
    ordered_ids = sorted(department_ids, key=lambda item: order.get(item, 10**9))
    names = [labels.get(item, "") for item in ordered_ids if labels.get(item)]
    full_label = "、".join(names)
    if not names:
        return "", ""
    if len(names) <= 3:
        return full_label, full_label
    return f"已选 {len(names)} 个部门：{'、'.join(names[:3])} 等", full_label


def save_person_rule_limits(db: Session, rule_id: int, score_option_ids: list[int], limits: list[str]) -> None:
    db.execute(delete(EvaluationPersonRuleOptionLimit).where(EvaluationPersonRuleOptionLimit.rule_id == rule_id))
    for option_id, max_people in parse_limit_map(score_option_ids, limits).items():
        if max_people is not None:
            db.add(EvaluationPersonRuleOptionLimit(rule_id=rule_id, score_option_id=option_id, max_people=max_people))


def save_person_position_option_limits(db: Session, evaluation_id: int, form) -> None:
    positions = db.scalars(select(Position).order_by(*positions_order())).all()
    position_ids = [position.id for position in positions]
    option_ids = [option.id for option in evaluation_person_options(db, evaluation_id)]
    db.execute(
        delete(EvaluationPersonPositionOptionLimit).where(
            EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id
        )
    )
    for index, option_id in enumerate(option_ids):
        selected_positions = [int(value) for value in form.getlist(f"position_ids_{option_id}") if str(value).isdigit()]
        if not selected_positions and f"has_option_{option_id}" not in form and f"position_ids_{option_id}" not in form:
            selected_positions = position_ids
        selected_positions = [position_id for position_id in dict.fromkeys(selected_positions) if position_id in position_ids]
        for position_id in selected_positions:
            raw_limit = str(form.get(f"limit_{option_id}_{position_id}", "")).strip()
            db.add(
                EvaluationPersonPositionOptionLimit(
                    evaluation_id=evaluation_id,
                    target_position_id=position_id,
                    score_option_id=option_id,
                    max_people=int(raw_limit) if raw_limit else None,
                )
            )


def save_department_option_limits(db: Session, evaluation_id: int, form) -> None:
    db.execute(
        delete(EvaluationDepartmentOptionLimit).where(
            EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id
        )
    )
    for option in evaluation_department_options(db, evaluation_id):
        raw_limit = str(form.get(f"limit_{option.id}", "")).strip()
        db.add(
            EvaluationDepartmentOptionLimit(
                evaluation_id=evaluation_id,
                score_option_id=option.id,
                max_count=int(raw_limit) if raw_limit else None,
            )
        )


def save_department_rule_limits(db: Session, rule_id: int, score_option_ids: list[int], limits: list[str]) -> None:
    db.execute(delete(EvaluationDepartmentRuleOptionLimit).where(EvaluationDepartmentRuleOptionLimit.rule_id == rule_id))
    for option_id, max_people in parse_limit_map(score_option_ids, limits).items():
        if max_people is not None:
            db.add(EvaluationDepartmentRuleOptionLimit(rule_id=rule_id, score_option_id=option_id, max_people=max_people))


def selected_reviewer_user_id(db: Session, reviewer_user_id: str, reviewer_position_id: int) -> int | None:
    if not reviewer_user_id:
        return None
    reviewer = db.get(User, int(reviewer_user_id))
    if not reviewer or reviewer.role != "user" or not reviewer.is_active:
        raise ValueError("指定评价人不存在或已停用。")
    if reviewer.position_id != reviewer_position_id:
        raise ValueError("指定评价人必须属于所选评分人职位。")
    return reviewer.id


def save_evaluation_person_options(db: Session, evaluation_id: int, option_ids: list[int]) -> None:
    option_ids = list(dict.fromkeys(option_ids))
    db.execute(delete(EvaluationScoreOption).where(EvaluationScoreOption.evaluation_id == evaluation_id))
    for index, option_id in enumerate(option_ids):
        db.add(EvaluationScoreOption(evaluation_id=evaluation_id, score_option_id=option_id, sort_order=index))
    rule_ids = db.scalars(select(EvaluationPersonRule.id).where(EvaluationPersonRule.evaluation_id == evaluation_id)).all()
    if rule_ids:
        stmt = delete(EvaluationPersonRuleOptionLimit).where(EvaluationPersonRuleOptionLimit.rule_id.in_(rule_ids))
        if option_ids:
            stmt = stmt.where(EvaluationPersonRuleOptionLimit.score_option_id.not_in(option_ids))
        db.execute(stmt)
    position_limit_stmt = delete(EvaluationPersonPositionOptionLimit).where(
        EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id
    )
    if option_ids:
        position_limit_stmt = position_limit_stmt.where(
            EvaluationPersonPositionOptionLimit.score_option_id.not_in(option_ids)
        )
    db.execute(position_limit_stmt)


def save_evaluation_department_options(db: Session, evaluation_id: int, option_ids: list[int]) -> None:
    option_ids = list(dict.fromkeys(option_ids))
    db.execute(delete(EvaluationDepartmentScoreOption).where(EvaluationDepartmentScoreOption.evaluation_id == evaluation_id))
    for index, option_id in enumerate(option_ids):
        db.add(EvaluationDepartmentScoreOption(evaluation_id=evaluation_id, score_option_id=option_id, sort_order=index))
    rule_ids = db.scalars(select(EvaluationDepartmentRule.id).where(EvaluationDepartmentRule.evaluation_id == evaluation_id)).all()
    if rule_ids:
        stmt = delete(EvaluationDepartmentRuleOptionLimit).where(EvaluationDepartmentRuleOptionLimit.rule_id.in_(rule_ids))
        if option_ids:
            stmt = stmt.where(EvaluationDepartmentRuleOptionLimit.score_option_id.not_in(option_ids))
        db.execute(stmt)
    limit_stmt = delete(EvaluationDepartmentOptionLimit).where(
        EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id
    )
    if option_ids:
        limit_stmt = limit_stmt.where(EvaluationDepartmentOptionLimit.score_option_id.not_in(option_ids))
    db.execute(limit_stmt)


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.cookies.get("user_id")
    if not user_id or not user_id.isdigit():
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        return None
    return user


def require_user(user: User | None = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def count_rows(db: Session, model: type, *conditions) -> int:
    return db.scalar(select(func.count(model.id)).where(*conditions)) or 0


def blocked_delete_response(path: str, name: str, references: list[str]) -> RedirectResponse:
    detail = "、".join(references)
    return flash(redirect(path), f"{name}已被引用，不能删除。请先处理相关数据：{detail}。", "error")


def department_delete_references(db: Session, department_id: int) -> list[str]:
    references = []
    checks = [
        ("下级部门", Department, Department.parent_id == department_id),
        ("人员", User, User.department_id == department_id),
        ("人员考核规则部门范围", EvaluationPersonRuleDepartment, EvaluationPersonRuleDepartment.department_id == department_id),
        ("部门考核规则", EvaluationDepartmentRule, EvaluationDepartmentRule.target_department_id == department_id),
        ("部门得分占比旧规则", EvaluationDepartmentShareRule, EvaluationDepartmentShareRule.department_id == department_id),
        ("手动部门得分", EvaluationDepartmentManualScore, EvaluationDepartmentManualScore.department_id == department_id),
        ("考核任务", EvaluationTask, EvaluationTask.target_department_id == department_id),
    ]
    for label, model, condition in checks:
        count = count_rows(db, model, condition)
        if count:
            references.append(f"{label}{count}条")
    return references


def position_delete_references(db: Session, position_id: int) -> list[str]:
    references = []
    checks = [
        ("人员", User, User.position_id == position_id),
        ("人员考核规则评分人", EvaluationPersonRule, EvaluationPersonRule.reviewer_position_id == position_id),
        ("人员考核规则被评人", EvaluationPersonRule, EvaluationPersonRule.target_position_id == position_id),
        ("人员评分限制", EvaluationPersonPositionOptionLimit, EvaluationPersonPositionOptionLimit.target_position_id == position_id),
        ("部门考核规则评分人", EvaluationDepartmentRule, EvaluationDepartmentRule.reviewer_position_id == position_id),
        ("部门得分占比规则", EvaluationDepartmentScoreShareRule, EvaluationDepartmentScoreShareRule.target_position_id == position_id),
        ("部门得分占比旧规则", EvaluationDepartmentShareRule, EvaluationDepartmentShareRule.target_position_id == position_id),
    ]
    for label, model, condition in checks:
        count = count_rows(db, model, condition)
        if count:
            references.append(f"{label}{count}条")
    return references


def score_option_delete_references(db: Session, option_id: int) -> list[str]:
    references = []
    checks = [
        ("人员评分选项", EvaluationScoreOption, EvaluationScoreOption.score_option_id == option_id),
        ("部门评分选项", EvaluationDepartmentScoreOption, EvaluationDepartmentScoreOption.score_option_id == option_id),
        ("人员评分限制", EvaluationPersonPositionOptionLimit, EvaluationPersonPositionOptionLimit.score_option_id == option_id),
        ("部门评分限制", EvaluationDepartmentOptionLimit, EvaluationDepartmentOptionLimit.score_option_id == option_id),
        ("人员规则旧限制", EvaluationPersonRuleOptionLimit, EvaluationPersonRuleOptionLimit.score_option_id == option_id),
        ("部门规则旧限制", EvaluationDepartmentRuleOptionLimit, EvaluationDepartmentRuleOptionLimit.score_option_id == option_id),
        ("已提交评分", EvaluationVote, EvaluationVote.score_option_id == option_id),
    ]
    for label, model, condition in checks:
        count = count_rows(db, model, condition)
        if count:
            references.append(f"{label}{count}条")
    return references


def archived_block_response(db: Session, evaluation_id: int, path: str = "/admin/evaluations") -> RedirectResponse | None:
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    if evaluation.archived:
        return flash(redirect(path), "已归档考核只能查看详情、复制或删除，不能再修改。", "error")
    return None


def delete_evaluation_data(db: Session, evaluation: Evaluation) -> None:
    person_rule_ids = db.scalars(select(EvaluationPersonRule.id).where(EvaluationPersonRule.evaluation_id == evaluation.id)).all()
    department_rule_ids = db.scalars(select(EvaluationDepartmentRule.id).where(EvaluationDepartmentRule.evaluation_id == evaluation.id)).all()
    if person_rule_ids:
        db.execute(delete(EvaluationPersonRuleDepartment).where(EvaluationPersonRuleDepartment.rule_id.in_(person_rule_ids)))
        db.execute(delete(EvaluationPersonRuleOptionLimit).where(EvaluationPersonRuleOptionLimit.rule_id.in_(person_rule_ids)))
    if department_rule_ids:
        db.execute(delete(EvaluationDepartmentRuleOptionLimit).where(EvaluationDepartmentRuleOptionLimit.rule_id.in_(department_rule_ids)))
    for model in (
        EvaluationVote,
        EvaluationReviewReopen,
        EvaluationTask,
        EvaluationScoreOption,
        EvaluationDepartmentScoreOption,
        EvaluationPersonPositionOptionLimit,
        EvaluationDepartmentOptionLimit,
        EvaluationDepartmentScoreShareRule,
        EvaluationDepartmentShareRule,
        EvaluationDepartmentManualScore,
        EvaluationPersonRule,
        EvaluationDepartmentRule,
        ArchivedPersonScore,
        ArchivedDepartmentScore,
        ArchivedVoteDetail,
        ArchivedRuleSnapshot,
        EvaluationAuditLog,
    ):
        db.execute(delete(model).where(model.evaluation_id == evaluation.id))
    db.delete(evaluation)


@app.get("/", response_class=HTMLResponse)
def index(user: User | None = Depends(current_user)):
    if not user:
        return redirect("/login")
    return redirect("/admin" if user.role == "admin" else "/app/evaluation")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html", {})


@app.post("/login")
def login(response: Response, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        target = redirect("/login")
        return flash(target, "用户名或密码错误。", "error")
    target = redirect("/admin" if user.role == "admin" else "/app/evaluation")
    target.set_cookie("user_id", str(user.id), httponly=True, samesite="lax")
    return target


@app.post("/logout")
def logout():
    response = redirect("/login")
    response.delete_cookie("user_id")
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(require_admin)):
    stats = {
        "departments": len(db.scalars(select(Department)).all()),
        "positions": len(db.scalars(select(Position)).all()),
        "users": len(db.scalars(select(User).where(User.role == "user")).all()),
        "evaluations": len(db.scalars(select(Evaluation)).all()),
    }
    evaluations = db.scalars(select(Evaluation).order_by(Evaluation.year.desc())).all()
    keyword = q.strip()
    filtered_evaluations = evaluations
    if keyword:
        filtered_evaluations = [
            item
            for item in evaluations
            if keyword in (item.name or "")
            or keyword in str(item.year)
            or keyword in ("进行中" if item.is_open else "未开放")
            or keyword in ("已归档" if item.archived else "")
        ]
    return render(request, "admin/dashboard.html", {
        "user": user,
        "stats": stats,
        "evaluations": evaluations,
        "filtered_evaluations": filtered_evaluations,
        "q": q,
    })


@app.get("/admin/departments", response_class=HTMLResponse)
def departments_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return render(request, "admin/departments.html", {"user": user, "departments": department_rows(db)})


@app.post("/admin/departments")
def create_department(name: str = Form(...), parent_id: str = Form(""), sort_order: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target_order = reserve_sort_order(db, Department, int(sort_order)) if sort_order else next_sort_order(db, Department)
    db.add(
        Department(
            name=name.strip(),
            parent_id=int(parent_id) if parent_id else None,
            sort_order=target_order,
        )
    )
    db.commit()
    return flash(redirect("/admin/departments"), "部门已创建。", "success")


@app.post("/admin/departments/{department_id}/update")
def update_department(department_id: int, name: str = Form(...), parent_id: str = Form(""), sort_order: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    department = db.get(Department, department_id)
    if not department:
        raise HTTPException(404)
    department.name = name.strip()
    department.parent_id = int(parent_id) if parent_id else None
    apply_sort_order(db, department, Department, sort_order)
    db.commit()
    return flash(redirect("/admin/departments"), "部门已更新。", "success")


@app.post("/admin/departments/{department_id}/delete")
def delete_department(department_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    department = db.get(Department, department_id)
    if department:
        references = department_delete_references(db, department_id)
        if references:
            return blocked_delete_response("/admin/departments", "部门", references)
        db.delete(department)
        db.commit()
    return flash(redirect("/admin/departments"), "部门已删除。", "success")


@app.get("/admin/positions", response_class=HTMLResponse)
def positions_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return render(request, "admin/positions.html", {"user": user, "positions": position_rows(db)})


@app.post("/admin/positions")
def create_position(name: str = Form(...), sort_order: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target_order = reserve_sort_order(db, Position, int(sort_order)) if sort_order else next_sort_order(db, Position)
    db.add(Position(name=name.strip(), sort_order=target_order))
    db.commit()
    return flash(redirect("/admin/positions"), "职位已创建。", "success")


@app.post("/admin/positions/{position_id}/update")
def update_position(position_id: int, name: str = Form(...), sort_order: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    position = db.get(Position, position_id)
    if position:
        position.name = name.strip()
        apply_sort_order(db, position, Position, sort_order)
        db.commit()
    return flash(redirect("/admin/positions"), "职位已更新。", "success")


@app.post("/admin/positions/{position_id}/delete")
def delete_position(position_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    position = db.get(Position, position_id)
    if position:
        references = position_delete_references(db, position_id)
        if references:
            return blocked_delete_response("/admin/positions", "职位", references)
        db.delete(position)
        db.commit()
    return flash(redirect("/admin/positions"), "职位已删除。", "success")


@app.get("/admin/users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    page_size = 10
    page = max(page, 1)
    users_stmt = (
        select(
            User.id,
            User.username,
            User.full_name,
            User.role,
            User.is_active,
            User.department_id,
            User.position_id,
            Department.name.label("department_name"),
            Position.name.label("position_name"),
        )
        .outerjoin(Department, User.department_id == Department.id)
        .outerjoin(Position, User.position_id == Position.id)
        .order_by(User.role, Department.sort_order, Department.id, Position.sort_order, Position.id, User.id)
    )
    count_stmt = select(func.count(User.id))
    if q:
        like = f"%{q}%"
        filter_clause = User.username.like(like) | User.full_name.like(like)
        users_stmt = (
            select(
                User.id,
                User.username,
                User.full_name,
                User.role,
                User.is_active,
                User.department_id,
                User.position_id,
                Department.name.label("department_name"),
                Position.name.label("position_name"),
            )
            .outerjoin(Department, User.department_id == Department.id)
            .outerjoin(Position, User.position_id == Position.id)
            .where(filter_clause)
            .order_by(User.role, Department.sort_order, Department.id, Position.sort_order, Position.id, User.id)
        )
        count_stmt = (
            select(func.count(User.id))
            .where(User.username.like(like) | User.full_name.like(like))
        )
    total_users = db.scalar(count_stmt) or 0
    total_pages = max((total_users + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    user_rows = db.execute(users_stmt.offset((page - 1) * page_size).limit(page_size)).all()
    users = [
        {
            "id": row.id,
            "username": row.username,
            "full_name": row.full_name,
            "role": row.role,
            "is_active": row.is_active,
            "department_id": row.department_id,
            "position_id": row.position_id,
            "department_name": row.department_name,
            "position_name": row.position_name,
        }
        for row in user_rows
    ]
    departments = department_rows(db)
    positions = position_rows(db)
    return render(request, "admin/users.html", {
        "user": user,
        "users": users,
        "q": q,
        "departments": departments,
        "positions": positions,
        "page": page,
        "total_pages": total_pages,
        "total_users": total_users,
        "page_size": page_size,
    })


@app.post("/admin/users")
def create_user(username: str = Form(...), full_name: str = Form(...), password: str = Form("123456"), role: str = Form("user"), department_id: str = Form(""), position_id: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    db.add(User(username=username.strip(), full_name=full_name.strip(), password_hash=hash_password(password or "123456"), role=role, department_id=int(department_id) if department_id else None, position_id=int(position_id) if position_id else None))
    db.commit()
    return flash(redirect("/admin/users"), "人员已创建。", "success")


@app.post("/admin/users/{target_id}/update")
def update_user(target_id: int, username: str = Form(...), full_name: str = Form(...), role: str = Form("user"), is_active: str = Form("off"), department_id: str = Form(""), position_id: str = Form(""), password: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, target_id)
    if not target:
        raise HTTPException(404)
    target.username = username.strip()
    target.full_name = full_name.strip()
    target.role = role
    target.is_active = is_active == "on"
    target.department_id = int(department_id) if department_id else None
    target.position_id = int(position_id) if position_id else None
    if password:
        target.password_hash = hash_password(password)
    db.commit()
    return flash(redirect("/admin/users"), "人员已更新。", "success")


@app.post("/admin/users/{target_id}/delete")
def delete_user(target_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    target = db.get(User, target_id)
    if target and target.id != user.id:
        db.delete(target)
        db.commit()
    return flash(redirect("/admin/users"), "人员已删除。", "success")


@app.get("/admin/score-options", response_class=HTMLResponse)
def score_options_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return render(request, "admin/score_options.html", {"user": user, "options": db.scalars(select(ScoreOption).order_by(ScoreOption.id)).all()})


@app.post("/admin/score-options")
def create_score_option(name: str = Form(...), value: float = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    db.add(ScoreOption(name=name.strip(), value=value))
    db.commit()
    return flash(redirect("/admin/score-options"), "评分选项已创建。", "success")


@app.post("/admin/score-options/{option_id}/update")
def update_score_option(option_id: int, name: str = Form(...), value: float = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    option = db.get(ScoreOption, option_id)
    if option:
        option.name = name.strip()
        option.value = value
        db.commit()
    return flash(redirect("/admin/score-options"), "评分选项已更新。", "success")


@app.post("/admin/score-options/{option_id}/delete")
def delete_score_option(option_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    option = db.get(ScoreOption, option_id)
    if option:
        references = score_option_delete_references(db, option_id)
        if references:
            return blocked_delete_response("/admin/score-options", "评分选项", references)
        db.delete(option)
        db.commit()
    return flash(redirect("/admin/score-options"), "评分选项已删除。", "success")


@app.get("/admin/evaluations", response_class=HTMLResponse)
def evaluations_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return render(request, "admin/evaluations/index.html", {"user": user, "evaluations": db.scalars(select(Evaluation).order_by(Evaluation.year.desc())).all()})


@app.get("/admin/evaluations/audit", response_class=HTMLResponse)
def evaluations_audit_page(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    start_year = datetime.utcnow().year - 2
    rows_stmt = (
        select(EvaluationAuditLog, Evaluation.name.label("evaluation_name"), Evaluation.year.label("evaluation_year"))
        .join(Evaluation, Evaluation.id == EvaluationAuditLog.evaluation_id)
        .where(Evaluation.year >= start_year)
    )
    if q:
        like = f"%{q}%"
        rows_stmt = rows_stmt.where(or_(
            Evaluation.name.like(like),
            EvaluationAuditLog.actor_name.like(like),
            EvaluationAuditLog.action.like(like),
            EvaluationAuditLog.detail.like(like),
            Evaluation.year.cast(String).like(like),
        ))
    rows_stmt = rows_stmt.order_by(EvaluationAuditLog.id.desc())
    total_logs = count_select(db, rows_stmt)
    page_info = pagination(total_logs, page, 20)
    rows = db.execute(
        rows_stmt
        .offset((page_info["page"] - 1) * page_info["page_size"])
        .limit(page_info["page_size"])
    ).all()
    q_query = f"&q={quote(q)}" if q else ""
    return render(request, "admin/evaluations/audit.html", {
        "user": user,
        "q": q,
        "q_query": q_query,
        "start_year": start_year,
        "rows": rows,
        "pagination": page_info,
    })


@app.post("/admin/evaluations")
def create_evaluation(year: int = Form(...), name: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    db.add(Evaluation(year=year, name=name.strip() or f"{year} 年考核"))
    db.commit()
    return flash(redirect("/admin/evaluations"), "考核已创建。", "success")


@app.get("/admin/evaluations/{evaluation_id}/settings", response_class=HTMLResponse)
def evaluation_settings(request: Request, evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "评分选项请在人员考核规则或部门考核规则中分别设置。", "info")


def reviewer_user_choices(db: Session, position_id: int) -> list[User]:
    return db.scalars(
        select(User)
        .where(
            User.role == "user",
            User.is_active.is_(True),
            User.position_id == position_id,
        )
        .order_by(User.full_name, User.id)
    ).all()


@app.get("/admin/positions/{position_id}/reviewer-users")
def reviewer_users_by_position(position_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    users = reviewer_user_choices(db, position_id)
    return [{"id": item.id, "name": item.full_name} for item in users]


def review_submissions_target(evaluation_id: int, page: int = 1, q: str = "") -> str:
    target = f"/admin/evaluations/{evaluation_id}/review-submissions?page={max(page, 1)}"
    if q:
        target += f"&q={quote(q)}"
    return target


@app.get("/admin/evaluations/{evaluation_id}/person-rules", response_class=HTMLResponse)
def evaluation_person_rules_page(request: Request, evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    departments = department_choice_rows(db)
    department_labels = {item["id"]: item["name"] for item in departments}
    department_order = {item["id"]: index for index, item in enumerate(departments)}
    person_rules = db.scalars(select(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == evaluation_id)).all()
    for rule in person_rules:
        rule.target_department_ids = [item.department_id for item in rule.target_departments]
        rule.target_department_summary, rule.target_department_label = department_selection_summary(rule.target_department_ids, department_labels, department_order)
        rule.reviewer_user_options = reviewer_user_choices(db, rule.reviewer_position_id)
    person_options = evaluation_person_options(db, evaluation_id)
    position_limit_rows = db.scalars(
        select(EvaluationPersonPositionOptionLimit).where(
            EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id,
            EvaluationPersonPositionOptionLimit.max_people.is_not(None),
        ).join(Position, Position.id == EvaluationPersonPositionOptionLimit.target_position_id)
        .join(ScoreOption, ScoreOption.id == EvaluationPersonPositionOptionLimit.score_option_id)
        .order_by(Position.sort_order, Position.id, ScoreOption.id)
    ).all()
    positions = db.scalars(select(Position).order_by(*positions_order())).all()
    initial_reviewer_users = reviewer_user_choices(db, positions[0].id) if positions else []
    return render(request, "admin/evaluations/person_rules.html", {
        "user": user,
        "evaluation": evaluation,
        "positions": positions,
        "initial_reviewer_users": initial_reviewer_users,
        "departments": departments,
        "score_options": db.scalars(select(ScoreOption).order_by(ScoreOption.id)).all(),
        "person_options": person_options,
        "person_option_ids": [item.id for item in person_options],
        "person_limit_rows": position_limit_rows,
        "person_rules": person_rules,
    })


@app.get("/admin/evaluations/{evaluation_id}/department-rules", response_class=HTMLResponse)
def evaluation_department_rules_page(request: Request, evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    departments = department_choice_rows(db)
    department_labels = {item["id"]: item["display_name"] for item in departments}
    department_rules = db.scalars(select(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == evaluation_id)).all()
    for rule in department_rules:
        rule.target_department_label = department_labels.get(rule.target_department_id, rule.target_department.name)
    department_options = evaluation_department_options(db, evaluation_id)
    department_limit_rows = db.scalars(
        select(EvaluationDepartmentOptionLimit).where(
            EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id,
            EvaluationDepartmentOptionLimit.max_count.is_not(None),
        ).join(ScoreOption, ScoreOption.id == EvaluationDepartmentOptionLimit.score_option_id)
        .order_by(ScoreOption.id)
    ).all()
    return render(request, "admin/evaluations/department_rules.html", {
        "user": user,
        "evaluation": evaluation,
        "positions": db.scalars(select(Position).order_by(*positions_order())).all(),
        "departments": departments,
        "score_options": db.scalars(select(ScoreOption).order_by(ScoreOption.id)).all(),
        "department_options": department_options,
        "department_option_ids": [item.id for item in department_options],
        "department_limit_rows": department_limit_rows,
        "department_rules": department_rules,
    })


@app.get("/admin/evaluations/{evaluation_id}/department-share-rules", response_class=HTMLResponse)
def evaluation_department_share_rules_page(request: Request, evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    rules = db.scalars(
        select(EvaluationDepartmentScoreShareRule)
        .where(EvaluationDepartmentScoreShareRule.evaluation_id == evaluation_id)
        .join(Position, Position.id == EvaluationDepartmentScoreShareRule.target_position_id)
        .order_by(Position.sort_order, Position.id)
    ).all()
    manual_scores = db.scalars(
        select(EvaluationDepartmentManualScore)
        .where(EvaluationDepartmentManualScore.evaluation_id == evaluation_id)
        .join(Department, Department.id == EvaluationDepartmentManualScore.department_id)
        .order_by(Department.sort_order, Department.id)
    ).all()
    return render(request, "admin/evaluations/department_share_rules.html", {
        "user": user,
        "evaluation": evaluation,
        "positions": db.scalars(select(Position).order_by(*positions_order())).all(),
        "departments": department_choice_rows(db),
        "share_rules": rules,
        "manual_scores": manual_scores,
    })


@app.post("/admin/evaluations/{evaluation_id}/settings/options")
def save_evaluation_options(evaluation_id: int, option_ids: list[int] = Form(default=[]), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "评分选项请在人员考核规则或部门考核规则中分别设置。", "info")


@app.post("/admin/evaluations/{evaluation_id}/settings/person-options")
async def save_person_options(request: Request, evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    form = await request.form()
    option_ids = [int(value) for value in form.getlist("option_ids") if str(value).isdigit()]
    save_evaluation_person_options(db, evaluation_id, option_ids)
    add_audit_log(db, evaluation_id, user, "保存人员评分选项", f"选项数量：{len(option_ids)}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "人员评分选项已保存。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/person-limits")
def add_person_limit(evaluation_id: int, target_position_id: int = Form(...), score_option_id: int = Form(...), max_people: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    existing = db.scalar(
        select(EvaluationPersonPositionOptionLimit).where(
            EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id,
            EvaluationPersonPositionOptionLimit.target_position_id == target_position_id,
            EvaluationPersonPositionOptionLimit.score_option_id == score_option_id,
        )
    )
    max_value = int(max_people) if max_people else None
    if existing:
        if max_value is None:
            db.delete(existing)
        else:
            existing.max_people = max_value
    elif max_value is not None:
        db.add(EvaluationPersonPositionOptionLimit(evaluation_id=evaluation_id, target_position_id=target_position_id, score_option_id=score_option_id, max_people=max_value))
    else:
        add_audit_log(db, evaluation_id, user, "保存人员评分限制", "未设置人数限制，默认不限制")
        db.commit()
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "未设置人数限制，默认不限制。", "info")
    add_audit_log(db, evaluation_id, user, "保存人员评分限制", f"职位ID：{target_position_id}；评分项ID：{score_option_id}；限制：{max_value}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "人员评分限制已保存。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/person-limits/{limit_id}/update")
def update_person_limit(evaluation_id: int, limit_id: int, target_position_id: int = Form(...), score_option_id: int = Form(...), max_people: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    limit = db.get(EvaluationPersonPositionOptionLimit, limit_id)
    if not limit or limit.evaluation_id != evaluation_id:
        raise HTTPException(404)
    max_value = int(max_people) if max_people else None
    existing = db.scalar(
        select(EvaluationPersonPositionOptionLimit).where(
            EvaluationPersonPositionOptionLimit.evaluation_id == evaluation_id,
            EvaluationPersonPositionOptionLimit.target_position_id == target_position_id,
            EvaluationPersonPositionOptionLimit.score_option_id == score_option_id,
            EvaluationPersonPositionOptionLimit.id != limit_id,
        )
    )
    if existing:
        if max_value is None:
            db.delete(existing)
        else:
            existing.max_people = max_value
        db.delete(limit)
    elif max_value is None:
        db.delete(limit)
    else:
        limit.target_position_id = target_position_id
        limit.score_option_id = score_option_id
        limit.max_people = max_value
    add_audit_log(db, evaluation_id, user, "更新人员评分限制", f"限制ID：{limit_id}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "人员评分限制已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/person-limits/{limit_id}/delete")
def delete_person_limit(evaluation_id: int, limit_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    limit = db.get(EvaluationPersonPositionOptionLimit, limit_id)
    if limit and limit.evaluation_id == evaluation_id:
        db.delete(limit)
        add_audit_log(db, evaluation_id, user, "删除人员评分限制", f"限制ID：{limit_id}")
        db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "人员评分限制已删除。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-options")
def save_department_options(evaluation_id: int, option_ids: list[int] = Form(default=[]), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    save_evaluation_department_options(db, evaluation_id, option_ids)
    add_audit_log(db, evaluation_id, user, "保存部门评分选项", f"选项数量：{len(option_ids)}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "部门评分选项已保存。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-limits")
def add_department_limit(evaluation_id: int, score_option_id: int = Form(...), max_count: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    option_enabled = db.scalar(
        select(EvaluationDepartmentScoreOption).where(
            EvaluationDepartmentScoreOption.evaluation_id == evaluation_id,
            EvaluationDepartmentScoreOption.score_option_id == score_option_id,
        )
    )
    if not option_enabled:
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "请先保存该部门评分选项后再设置数量限制。", "error")
    existing = db.scalar(
        select(EvaluationDepartmentOptionLimit).where(
            EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id,
            EvaluationDepartmentOptionLimit.score_option_id == score_option_id,
        )
    )
    max_value = int(max_count) if max_count else None
    if existing:
        if max_value is None:
            db.delete(existing)
        else:
            existing.max_count = max_value
    elif max_value is not None:
        db.add(EvaluationDepartmentOptionLimit(evaluation_id=evaluation_id, score_option_id=score_option_id, max_count=max_value))
    else:
        add_audit_log(db, evaluation_id, user, "保存部门评分限制", "未设置数量限制，默认不限制")
        db.commit()
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "未设置数量限制，默认不限制。", "info")
    add_audit_log(db, evaluation_id, user, "保存部门评分限制", f"评分项ID：{score_option_id}；限制：{max_value}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "部门评分限制已保存。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-limits/{limit_id}/update")
def update_department_limit(evaluation_id: int, limit_id: int, score_option_id: int = Form(...), max_count: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    limit = db.get(EvaluationDepartmentOptionLimit, limit_id)
    if not limit or limit.evaluation_id != evaluation_id:
        raise HTTPException(404)
    option_enabled = db.scalar(
        select(EvaluationDepartmentScoreOption).where(
            EvaluationDepartmentScoreOption.evaluation_id == evaluation_id,
            EvaluationDepartmentScoreOption.score_option_id == score_option_id,
        )
    )
    if not option_enabled:
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "请先保存该部门评分选项后再设置数量限制。", "error")
    max_value = int(max_count) if max_count else None
    existing = db.scalar(
        select(EvaluationDepartmentOptionLimit).where(
            EvaluationDepartmentOptionLimit.evaluation_id == evaluation_id,
            EvaluationDepartmentOptionLimit.score_option_id == score_option_id,
            EvaluationDepartmentOptionLimit.id != limit_id,
        )
    )
    if existing:
        if max_value is None:
            db.delete(existing)
        else:
            existing.max_count = max_value
        db.delete(limit)
    elif max_value is None:
        db.delete(limit)
    else:
        limit.score_option_id = score_option_id
        limit.max_count = max_value
    add_audit_log(db, evaluation_id, user, "更新部门评分限制", f"限制ID：{limit_id}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "部门评分限制已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-limits/{limit_id}/delete")
def delete_department_limit(evaluation_id: int, limit_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    limit = db.get(EvaluationDepartmentOptionLimit, limit_id)
    if limit and limit.evaluation_id == evaluation_id:
        db.delete(limit)
        add_audit_log(db, evaluation_id, user, "删除部门评分限制", f"限制ID：{limit_id}")
        db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "部门评分限制已删除。", "success")


@app.post("/admin/evaluations/{evaluation_id}/copy")
def copy_evaluation(evaluation_id: int, year: int = Form(...), name: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    source = db.get(Evaluation, evaluation_id)
    if not source:
        raise HTTPException(404)
    target = Evaluation(year=year, name=name.strip() or f"{source.name} 副本")
    db.add(target)
    db.flush()
    for index, option in enumerate(evaluation_person_options(db, source.id)):
        db.add(EvaluationScoreOption(evaluation_id=target.id, score_option_id=option.id, sort_order=index))
    person_position_limits = db.scalars(
        select(EvaluationPersonPositionOptionLimit).where(
            EvaluationPersonPositionOptionLimit.evaluation_id == source.id,
            EvaluationPersonPositionOptionLimit.max_people.is_not(None),
        )
    ).all()
    for limit in person_position_limits:
        db.add(
            EvaluationPersonPositionOptionLimit(
                evaluation_id=target.id,
                target_position_id=limit.target_position_id,
                score_option_id=limit.score_option_id,
                max_people=limit.max_people,
            )
        )
    for index, option in enumerate(evaluation_department_options(db, source.id)):
        db.add(EvaluationDepartmentScoreOption(evaluation_id=target.id, score_option_id=option.id, sort_order=index))
    department_limits = db.scalars(
        select(EvaluationDepartmentOptionLimit).where(
            EvaluationDepartmentOptionLimit.evaluation_id == source.id,
            EvaluationDepartmentOptionLimit.max_count.is_not(None),
        )
    ).all()
    for limit in department_limits:
        db.add(
            EvaluationDepartmentOptionLimit(
                evaluation_id=target.id,
                score_option_id=limit.score_option_id,
                max_count=limit.max_count,
            )
        )
    person_rule_map: dict[int, int] = {}
    person_rules = db.scalars(select(EvaluationPersonRule).where(EvaluationPersonRule.evaluation_id == source.id)).all()
    for rule in person_rules:
        copied = EvaluationPersonRule(
            evaluation_id=target.id,
            reviewer_position_id=rule.reviewer_position_id,
            reviewer_user_id=rule.reviewer_user_id,
            target_position_id=rule.target_position_id,
            score_group=rule.score_group,
            scope_type=rule.scope_type,
            weight=rule.weight,
        )
        db.add(copied)
        db.flush()
        person_rule_map[rule.id] = copied.id
        for department in rule.target_departments:
            db.add(EvaluationPersonRuleDepartment(rule_id=copied.id, department_id=department.department_id))

    department_rules = db.scalars(select(EvaluationDepartmentRule).where(EvaluationDepartmentRule.evaluation_id == source.id)).all()
    for rule in department_rules:
        copied = EvaluationDepartmentRule(
            evaluation_id=target.id,
            reviewer_position_id=rule.reviewer_position_id,
            target_department_id=rule.target_department_id,
            weight=rule.weight,
        )
        db.add(copied)
        db.flush()
    share_rules = db.scalars(
        select(EvaluationDepartmentScoreShareRule).where(
            EvaluationDepartmentScoreShareRule.evaluation_id == source.id
        )
    ).all()
    for rule in share_rules:
        db.add(
            EvaluationDepartmentScoreShareRule(
                evaluation_id=target.id,
                target_position_id=rule.target_position_id,
                weight=rule.weight,
            )
        )
    manual_scores = db.scalars(
        select(EvaluationDepartmentManualScore).where(
            EvaluationDepartmentManualScore.evaluation_id == source.id
        )
    ).all()
    for item in manual_scores:
        db.add(
            EvaluationDepartmentManualScore(
                evaluation_id=target.id,
                department_id=item.department_id,
                score=item.score,
            )
        )
    db.commit()
    return flash(redirect("/admin/evaluations"), "考核规则已复制。", "success")


@app.post("/admin/evaluations/{evaluation_id}/delete")
def delete_evaluation(evaluation_id: int, admin_password: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    if evaluation.archived and not verify_password(admin_password, user.password_hash):
        return flash(redirect("/admin/evaluations"), "删除已归档考核前请输入当前管理员密码。", "error")
    add_audit_log(db, evaluation_id, user, "删除考核", f"{evaluation.name}（{evaluation.year}）")
    db.flush()
    delete_evaluation_data(db, evaluation)
    db.commit()
    return flash(redirect("/admin/evaluations"), "考核已删除。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/person-rules")
def add_person_rule(
    evaluation_id: int,
    reviewer_position_id: int = Form(...),
    reviewer_user_id: str = Form(""),
    target_position_id: int = Form(...),
    score_group: str = Form(""),
    scope_type: str = Form("selected_departments"),
    target_department_ids: list[int] = Form(default=[]),
    weight: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        resolved_reviewer_user_id = selected_reviewer_user_id(db, reviewer_user_id, reviewer_position_id)
    except ValueError as exc:
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), str(exc), "error")
    rule = EvaluationPersonRule(
        evaluation_id=evaluation_id,
        reviewer_position_id=reviewer_position_id,
        reviewer_user_id=resolved_reviewer_user_id,
        target_position_id=target_position_id,
        score_group=score_group.strip(),
        scope_type=scope_type,
        weight=weight,
    )
    db.add(rule)
    db.flush()
    for department_id in target_department_ids:
        db.add(EvaluationPersonRuleDepartment(rule_id=rule.id, department_id=department_id))
    add_audit_log(db, evaluation_id, user, "新增人员考核规则", f"规则ID：{rule.id}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "人员考核规则已添加。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/person-rules/{rule_id}/update")
def update_person_rule(
    evaluation_id: int,
    rule_id: int,
    reviewer_position_id: int = Form(...),
    reviewer_user_id: str = Form(""),
    target_position_id: int = Form(...),
    score_group: str = Form(""),
    scope_type: str = Form("selected_departments"),
    target_department_ids: list[int] = Form(default=[]),
    weight: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    rule = db.get(EvaluationPersonRule, rule_id)
    if not rule or rule.evaluation_id != evaluation_id:
        raise HTTPException(404)
    try:
        resolved_reviewer_user_id = selected_reviewer_user_id(db, reviewer_user_id, reviewer_position_id)
    except ValueError as exc:
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), str(exc), "error")
    rule.reviewer_position_id = reviewer_position_id
    rule.reviewer_user_id = resolved_reviewer_user_id
    rule.target_position_id = target_position_id
    rule.score_group = score_group.strip()
    rule.scope_type = scope_type
    rule.weight = weight
    db.execute(delete(EvaluationPersonRuleDepartment).where(EvaluationPersonRuleDepartment.rule_id == rule.id))
    for department_id in target_department_ids:
        db.add(EvaluationPersonRuleDepartment(rule_id=rule.id, department_id=department_id))
    add_audit_log(db, evaluation_id, user, "更新人员考核规则", f"规则ID：{rule_id}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/person-rules"), "人员考核规则已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-rules")
def add_department_rule(
    evaluation_id: int,
    reviewer_position_id: int = Form(...),
    target_department_ids: list[int] = Form(default=[]),
    target_department_id: str = Form(""),
    weight: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    department_ids = target_department_ids_from_form(target_department_ids, target_department_id)
    if not department_ids:
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "请选择被评部门。", "error")
    for department_id in department_ids:
        rule = EvaluationDepartmentRule(evaluation_id=evaluation_id, reviewer_position_id=reviewer_position_id, target_department_id=department_id, weight=weight)
        db.add(rule)
    add_audit_log(db, evaluation_id, user, "新增部门考核规则", f"部门数量：{len(department_ids)}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "部门考核规则已添加。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-rules/{rule_id}/update")
def update_department_rule(
    evaluation_id: int,
    rule_id: int,
    reviewer_position_id: int = Form(...),
    target_department_ids: list[int] = Form(default=[]),
    target_department_id: str = Form(""),
    weight: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    rule = db.get(EvaluationDepartmentRule, rule_id)
    if not rule or rule.evaluation_id != evaluation_id:
        raise HTTPException(404)
    department_ids = target_department_ids_from_form(target_department_ids, target_department_id)
    if not department_ids:
        return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "请选择被评部门。", "error")
    rule.reviewer_position_id = reviewer_position_id
    rule.target_department_id = department_ids[0]
    rule.weight = weight
    for department_id in department_ids[1:]:
        copied = EvaluationDepartmentRule(evaluation_id=evaluation_id, reviewer_position_id=reviewer_position_id, target_department_id=department_id, weight=weight)
        db.add(copied)
    add_audit_log(db, evaluation_id, user, "更新部门考核规则", f"规则ID：{rule_id}；部门数量：{len(department_ids)}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-rules"), "部门考核规则已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-share-rules")
def add_department_share_rule(
    evaluation_id: int,
    target_position_id: int = Form(...),
    weight: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    existing = db.scalar(
        select(EvaluationDepartmentScoreShareRule).where(
            EvaluationDepartmentScoreShareRule.evaluation_id == evaluation_id,
            EvaluationDepartmentScoreShareRule.target_position_id == target_position_id,
        )
    )
    if existing:
        existing.weight = weight
    else:
        db.add(
            EvaluationDepartmentScoreShareRule(
                evaluation_id=evaluation_id,
                target_position_id=target_position_id,
                weight=weight,
            )
        )
    add_audit_log(db, evaluation_id, user, "保存部门得分占比规则", f"职位ID：{target_position_id}；权重：{weight}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-share-rules"), "部门得分占比规则已保存。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-share-rules/{rule_id}/update")
def update_department_share_rule(
    evaluation_id: int,
    rule_id: int,
    target_position_id: int = Form(...),
    weight: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    rule = db.get(EvaluationDepartmentScoreShareRule, rule_id)
    if not rule or rule.evaluation_id != evaluation_id:
        raise HTTPException(404)
    existing = db.scalar(
        select(EvaluationDepartmentScoreShareRule).where(
            EvaluationDepartmentScoreShareRule.evaluation_id == evaluation_id,
            EvaluationDepartmentScoreShareRule.target_position_id == target_position_id,
            EvaluationDepartmentScoreShareRule.id != rule_id,
        )
    )
    if existing:
        existing.weight = weight
        db.delete(rule)
    else:
        rule.target_position_id = target_position_id
        rule.weight = weight
    add_audit_log(db, evaluation_id, user, "更新部门得分占比规则", f"规则ID：{rule_id}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-share-rules"), "部门得分占比规则已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/department-share-rules/{rule_id}/delete")
def delete_department_share_rule(evaluation_id: int, rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rule = db.get(EvaluationDepartmentScoreShareRule, rule_id)
    if rule and rule.evaluation_id == evaluation_id:
        db.delete(rule)
        add_audit_log(db, evaluation_id, user, "删除部门得分占比规则", f"规则ID：{rule_id}")
        db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-share-rules"), "部门得分占比规则已删除。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/manual-department-scores")
def add_manual_department_score(evaluation_id: int, department_id: int = Form(...), score: float = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    existing = db.scalar(
        select(EvaluationDepartmentManualScore).where(
            EvaluationDepartmentManualScore.evaluation_id == evaluation_id,
            EvaluationDepartmentManualScore.department_id == department_id,
        )
    )
    if existing:
        existing.score = score
    else:
        db.add(EvaluationDepartmentManualScore(evaluation_id=evaluation_id, department_id=department_id, score=score))
    add_audit_log(db, evaluation_id, user, "保存手动部门得分", f"部门ID：{department_id}；得分：{score}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-share-rules"), "手动部门得分已保存。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/manual-department-scores/{score_id}/update")
def update_manual_department_score(evaluation_id: int, score_id: int, department_id: int = Form(...), score: float = Form(...), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    item = db.get(EvaluationDepartmentManualScore, score_id)
    if not item or item.evaluation_id != evaluation_id:
        raise HTTPException(404)
    existing = db.scalar(
        select(EvaluationDepartmentManualScore).where(
            EvaluationDepartmentManualScore.evaluation_id == evaluation_id,
            EvaluationDepartmentManualScore.department_id == department_id,
            EvaluationDepartmentManualScore.id != score_id,
        )
    )
    if existing:
        existing.score = score
        db.delete(item)
    else:
        item.department_id = department_id
        item.score = score
    add_audit_log(db, evaluation_id, user, "更新手动部门得分", f"记录ID：{score_id}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-share-rules"), "手动部门得分已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/manual-department-scores/{score_id}/delete")
def delete_manual_department_score(evaluation_id: int, score_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    item = db.get(EvaluationDepartmentManualScore, score_id)
    if item and item.evaluation_id == evaluation_id:
        db.delete(item)
        add_audit_log(db, evaluation_id, user, "删除手动部门得分", f"记录ID：{score_id}")
        db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/department-share-rules"), "手动部门得分已删除。", "success")


@app.post("/admin/evaluations/{evaluation_id}/settings/{kind}/{rule_id}/delete")
def delete_rule(evaluation_id: int, kind: str, rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    model = EvaluationPersonRule if kind == "person" else EvaluationDepartmentRule
    rule = db.get(model, rule_id)
    if rule:
        db.delete(rule)
        add_audit_log(db, evaluation_id, user, "删除考核规则", f"类型：{kind}；规则ID：{rule_id}")
        db.commit()
    target = "person-rules" if kind == "person" else "department-rules"
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/{target}"), "规则已删除。", "success")


@app.post("/admin/evaluations/{evaluation_id}/generate-tasks")
def generate_evaluation_tasks(evaluation_id: int, confirm_action: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    existing_tasks = db.scalar(select(func.count(EvaluationTask.id)).where(EvaluationTask.evaluation_id == evaluation_id)) or 0
    if existing_tasks and confirm_action != "yes":
        return flash(redirect("/admin/evaluations"), "重新生成任务会覆盖现有任务和评分，请在确认弹窗中操作。", "error")
    count = generate_tasks(db, evaluation)
    add_audit_log(db, evaluation_id, user, "生成考核任务", f"生成任务数：{count}；覆盖前任务数：{existing_tasks}")
    db.commit()
    return flash(redirect("/admin/evaluations"), f"已生成 {count} 个考核任务。", "success")


@app.post("/admin/evaluations/{evaluation_id}/toggle-open")
def toggle_evaluation(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation:
        evaluation.is_open = not evaluation.is_open
        add_audit_log(db, evaluation_id, user, "更新考核状态", "开放考核" if evaluation.is_open else "关闭考核")
        db.commit()
    return flash(redirect("/admin/evaluations"), "考核状态已更新。", "success")


@app.post("/admin/evaluations/{evaluation_id}/archive")
def archive(evaluation_id: int, confirm_action: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    if confirm_action != "yes":
        return flash(redirect("/admin/evaluations"), "归档会固化当前分数和规则快照，请在确认弹窗中操作。", "error")
    progress = evaluation_task_progress(db, evaluation_id)
    if not progress["complete"]:
        reopen_hint = f"；待重新提交 {progress['pending_reopens']} 人" if progress["pending_reopens"] else ""
        return flash(redirect("/admin/evaluations"), f"所有考核任务完成后才能归档。当前完成 {progress['submitted_tasks']} / {progress['total_tasks']}{reopen_hint}。", "error")
    try:
        archive_evaluation(db, evaluation)
    except ValueError as exc:
        return flash(redirect("/admin/evaluations"), str(exc), "error")
    add_audit_log(db, evaluation_id, user, "归档考核", f"任务完成：{progress['submitted_tasks']} / {progress['total_tasks']}")
    db.commit()
    return flash(redirect(f"/admin/evaluations/{evaluation_id}/details"), "归档统计已完成。", "success")


@app.get("/admin/evaluations/{evaluation_id}/live-stats", response_class=HTMLResponse)
def evaluation_live_stats(
    request: Request,
    evaluation_id: int,
    q: str = "",
    people_page: int = 1,
    details_page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
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
    people, people_pagination = paginate_items(people, people_page, 10)
    details, details_pagination = paginate_items(details, details_page, 20)
    q_query = f"&q={quote(q)}" if q else ""
    return render(request, "admin/evaluations/live_stats.html", {
        "user": user,
        "evaluation": evaluation,
        "q": q,
        "q_query": q_query,
        "people": people,
        "people_pagination": people_pagination,
        "departments": departments,
        "details": details,
        "details_pagination": details_pagination,
        "stats": result,
    })


@app.get("/admin/evaluations/{evaluation_id}/review-submissions", response_class=HTMLResponse)
def review_submissions(request: Request, evaluation_id: int, q: str = "", page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    tasks = db.scalars(
        select(EvaluationTask).where(EvaluationTask.evaluation_id == evaluation_id).order_by(EvaluationTask.reviewer_id, EvaluationTask.id)
    ).all()
    votes_by_reviewer: dict[int, int] = {}
    vote_rows = db.execute(
        select(EvaluationVote.reviewer_id, func.count(EvaluationVote.id))
        .where(EvaluationVote.evaluation_id == evaluation_id)
        .group_by(EvaluationVote.reviewer_id)
    ).all()
    for reviewer_id, count in vote_rows:
        votes_by_reviewer[reviewer_id] = count
    reopen_rows = db.scalars(
        select(EvaluationReviewReopen).where(EvaluationReviewReopen.evaluation_id == evaluation_id)
    ).all()
    reopen_by_reviewer = {item.reviewer_id: item for item in reopen_rows}
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
        row = {
            "reviewer": reviewer,
            "task_count": len(reviewer_tasks),
            "submitted_count": submitted_count,
            "reopened": reopened,
            "status_label": status_label,
            "can_reopen": evaluation.is_open and not evaluation.archived and submitted_count >= len(reviewer_tasks) and not reopened,
            "can_cancel": evaluation.is_open and not evaluation.archived and reopened is not None,
        }
        if q:
            keyword = q.strip()
            department_name = reviewer.department.name if reviewer.department else ""
            position_name = reviewer.position.name if reviewer.position else ""
            if keyword not in reviewer.full_name and keyword not in department_name and keyword not in position_name:
                continue
        rows.append(row)

    rows, rows_pagination = paginate_items(rows, page, 10)
    q_query = f"&q={quote(q)}" if q else ""
    return render(request, "admin/evaluations/review_submissions.html", {
        "user": user,
        "evaluation": evaluation,
        "q": q,
        "q_query": q_query,
        "rows": rows,
        "rows_pagination": rows_pagination,
    })


@app.post("/admin/evaluations/{evaluation_id}/review-submissions/{reviewer_id}/reopen")
def reopen_review_submission(
    evaluation_id: int,
    reviewer_id: int,
    reason: str = Form(""),
    page: int = Form(1),
    q: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    evaluation = db.get(Evaluation, evaluation_id)
    reviewer = db.get(User, reviewer_id)
    if not evaluation or not reviewer:
        raise HTTPException(404)
    target = review_submissions_target(evaluation_id, page, q)
    if not evaluation.is_open or evaluation.archived:
        return flash(redirect(target), "只有考核开放且未归档时，才能允许用户重新修改评分。", "error")
    task_count = db.scalar(
        select(func.count(EvaluationTask.id)).where(
            EvaluationTask.evaluation_id == evaluation_id,
            EvaluationTask.reviewer_id == reviewer_id,
        )
    ) or 0
    vote_count = db.scalar(
        select(func.count(EvaluationVote.id)).where(
            EvaluationVote.evaluation_id == evaluation_id,
            EvaluationVote.reviewer_id == reviewer_id,
        )
    ) or 0
    if not task_count or vote_count < task_count:
        return flash(redirect(target), "该用户尚未完整提交评分，不能退回修改。", "error")
    existing = db.scalar(
        select(EvaluationReviewReopen).where(
            EvaluationReviewReopen.evaluation_id == evaluation_id,
            EvaluationReviewReopen.reviewer_id == reviewer_id,
        )
    )
    if existing:
        existing.reason = reason
        existing.created_by = user.id
    else:
        db.add(EvaluationReviewReopen(evaluation_id=evaluation_id, reviewer_id=reviewer_id, created_by=user.id, reason=reason))
    add_audit_log(db, evaluation_id, user, "允许重新修改评分", f"评分人：{reviewer.full_name}")
    db.commit()
    return flash(redirect(target), f"已允许 {reviewer.full_name} 重新修改评分。", "success")


@app.post("/admin/evaluations/{evaluation_id}/review-submissions/{reviewer_id}/cancel")
def cancel_reopen_review_submission(
    evaluation_id: int,
    reviewer_id: int,
    page: int = Form(1),
    q: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    target = review_submissions_target(evaluation_id, page, q)
    if not evaluation.is_open or evaluation.archived:
        return flash(redirect(target), "只有考核开放且未归档时，才能取消重新修改权限。", "error")
    db.execute(
        delete(EvaluationReviewReopen).where(
            EvaluationReviewReopen.evaluation_id == evaluation_id,
            EvaluationReviewReopen.reviewer_id == reviewer_id,
        )
    )
    add_audit_log(db, evaluation_id, user, "取消重新修改评分", f"评分人ID：{reviewer_id}")
    db.commit()
    return flash(redirect(target), "已取消重新修改权限。", "success")


@app.get("/admin/evaluations/{evaluation_id}/details", response_class=HTMLResponse)
def evaluation_details(
    request: Request,
    evaluation_id: int,
    q: str = "",
    people_page: int = 1,
    details_page: int = 1,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation:
        raise HTTPException(404)
    people_stmt = select(ArchivedPersonScore).where(ArchivedPersonScore.evaluation_id == evaluation_id)
    departments_stmt = select(ArchivedDepartmentScore).where(ArchivedDepartmentScore.evaluation_id == evaluation_id)
    details_stmt = select(ArchivedVoteDetail).where(ArchivedVoteDetail.evaluation_id == evaluation_id)
    if q:
        like = f"%{q}%"
        people_stmt = people_stmt.where(ArchivedPersonScore.full_name.like(like) | ArchivedPersonScore.department_name.like(like) | ArchivedPersonScore.position_name.like(like))
        departments_stmt = departments_stmt.where(ArchivedDepartmentScore.department_name.like(like))
        details_stmt = details_stmt.where(or_(
            ArchivedVoteDetail.reviewer_name.like(like),
            ArchivedVoteDetail.target_name.like(like),
            ArchivedVoteDetail.target_department_name.like(like),
            ArchivedVoteDetail.target_position_name.like(like),
            ArchivedVoteDetail.option_name.like(like),
            ArchivedVoteDetail.rule_label.like(like),
        ))
    people_total = count_select(db, people_stmt)
    people_pagination = pagination(people_total, people_page, 10)
    details_total = count_select(db, details_stmt)
    details_pagination = pagination(details_total, details_page, 20)
    q_query = f"&q={quote(q)}" if q else ""
    snapshots = db.scalars(
        select(ArchivedRuleSnapshot)
        .where(ArchivedRuleSnapshot.evaluation_id == evaluation_id)
        .order_by(ArchivedRuleSnapshot.id)
    ).all()
    return render(request, "admin/evaluations/details.html", {
        "user": user,
        "evaluation": evaluation,
        "q": q,
        "q_query": q_query,
        "people": db.scalars(
            people_stmt
            .order_by(ArchivedPersonScore.final_score.desc())
            .offset((people_pagination["page"] - 1) * people_pagination["page_size"])
            .limit(people_pagination["page_size"])
        ).all(),
        "people_pagination": people_pagination,
        "departments": db.scalars(departments_stmt.order_by(ArchivedDepartmentScore.final_score.desc())).all(),
        "details": db.scalars(
            details_stmt
            .order_by(ArchivedVoteDetail.id.desc())
            .offset((details_pagination["page"] - 1) * details_pagination["page_size"])
            .limit(details_pagination["page_size"])
        ).all(),
        "details_pagination": details_pagination,
        "snapshots": snapshots,
        "snapshot_preview": snapshot_preview,
    })


def current_open_evaluation(db: Session) -> Evaluation | None:
    return db.scalar(select(Evaluation).where(Evaluation.is_open.is_(True)).order_by(Evaluation.year.desc()))


@app.get("/app/evaluation", response_class=HTMLResponse)
def app_evaluation(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if user.role == "admin":
        return redirect("/admin")
    evaluation = current_open_evaluation(db)
    if not evaluation:
        return render(request, "app/evaluation.html", {"user": user, "evaluation": None})
    tasks = db.scalars(select(EvaluationTask).where(EvaluationTask.evaluation_id == evaluation.id, EvaluationTask.reviewer_id == user.id).order_by(EvaluationTask.task_type.desc(), EvaluationTask.id)).all()
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
    return render(request, "app/evaluation.html", {
        "user": user,
        "evaluation": evaluation,
        "tasks": tasks,
        "task_groups": task_groups(db, tasks),
        "options_by_task": task_options_map(db, tasks),
        "submitted": submitted and not reopened,
        "reopened": reopened,
        "current_choices": current_choices,
        "limit_map": task_limit_map(db, evaluation.id),
    })


@app.post("/app/evaluation/submit")
async def submit_evaluation(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    evaluation = current_open_evaluation(db)
    if not evaluation:
        return flash(redirect("/app/evaluation"), "当前不在考评期间。", "error")
    form = await request.form()
    choices = {int(key.split("_", 1)[1]): int(value) for key, value in form.items() if key.startswith("task_") and value}
    errors = validate_vote_payload(db, evaluation, user, choices)
    if errors:
        return flash(redirect("/app/evaluation"), errors[0], "error")
    submit_votes(db, evaluation, user, choices)
    return flash(redirect("/app/evaluation"), "考核已提交。", "success")


@app.get("/app/password", response_class=HTMLResponse)
def password_page(request: Request, user: User = Depends(require_user)):
    return render(request, "app/password.html", {"user": user})


@app.post("/app/password")
def change_password(old_password: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not verify_password(old_password, user.password_hash):
        return flash(redirect("/app/password"), "原密码不正确。", "error")
    user.password_hash = hash_password(new_password)
    db.commit()
    return flash(redirect("/app/evaluation"), "密码已修改。", "success")
