from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.api.deps import require_api_admin
from app.api.schemas import (
    DepartmentChoice,
    DepartmentCreate,
    DepartmentRow,
    DepartmentUpdate,
    MessageResponse,
    Pagination,
    PositionCreate,
    PositionRow,
    PositionUpdate,
    ReviewerUserRow,
    ScoreOptionCreate,
    ScoreOptionRow,
    ScoreOptionUpdate,
    UserCreate,
    UserListResponse,
    UserRow,
    UserUpdate,
)
from app.database import get_db
from app.models import (
    Department,
    EvaluationDepartmentManualScore,
    EvaluationDepartmentOptionLimit,
    EvaluationDepartmentRule,
    EvaluationDepartmentRuleOptionLimit,
    EvaluationDepartmentScoreOption,
    EvaluationDepartmentScoreShareRule,
    EvaluationDepartmentShareRule,
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
    UserSession,
)
from app.security import hash_password

router = APIRouter(tags=["master-data"])


def pagination(total: int, page: int, page_size: int) -> Pagination:
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(page, 1), total_pages)
    return Pagination(page=page, total_pages=total_pages, total=total, page_size=page_size)


def count_rows(db: Session, model: type, *conditions) -> int:
    return db.scalar(select(func.count(model.id)).where(*conditions)) or 0


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


def apply_sort_order(db: Session, item, model: type, sort_order: int | None) -> None:
    if sort_order is None:
        return
    rows = normalize_sort_orders(db, model)
    ordered = [row for row in rows if row.id != item.id]
    target_index = min(max(sort_order - 1, 0), len(ordered))
    ordered.insert(target_index, item)
    for index, row in enumerate(ordered, start=1):
        row.sort_order = index


def validate_department_parent(db: Session, parent_id: int | None, department_id: int | None = None) -> None:
    if parent_id is None:
        return
    parent = db.get(Department, parent_id)
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上级部门不存在。")
    if parent_id == department_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="部门不能设置为自身的上级部门。")

    current = parent
    visited: set[int] = set()
    while current and current.id not in visited:
        if current.id == department_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="部门不能设置为其下级部门的子部门。")
        visited.add(current.id)
        current = db.get(Department, current.parent_id) if current.parent_id else None


def validate_department_name(
    db: Session,
    name: str,
    parent_id: int | None,
    department_id: int | None = None,
) -> str:
    normalized_name = name.strip()
    condition = Department.parent_id == parent_id if parent_id is not None else Department.parent_id.is_(None)
    stmt = select(Department.id).where(Department.name == normalized_name, condition)
    if department_id is not None:
        stmt = stmt.where(Department.id != department_id)
    if db.scalar(stmt) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同一上级部门下已存在同名部门。")
    return normalized_name


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


def department_branch_ids(db: Session, department_id: int) -> set[int]:
    if not db.get(Department, department_id):
        raise HTTPException(status_code=404, detail="部门不存在。")
    children_by_parent: dict[int, list[int]] = {}
    for child_id, parent_id in db.execute(select(Department.id, Department.parent_id)).all():
        if parent_id is not None:
            children_by_parent.setdefault(parent_id, []).append(child_id)
    branch = {department_id}
    pending = [department_id]
    while pending:
        children = children_by_parent.get(pending.pop(), [])
        branch.update(children)
        pending.extend(children)
    return branch


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


def user_delete_references(db: Session, user_id: int) -> list[str]:
    references = []
    checks = [
        ("指定评价人规则", EvaluationPersonRule, EvaluationPersonRule.reviewer_user_id == user_id),
        ("考核任务", EvaluationTask, or_(EvaluationTask.reviewer_id == user_id, EvaluationTask.target_user_id == user_id)),
        ("已提交评分", EvaluationVote, EvaluationVote.reviewer_id == user_id),
        ("评分修改记录", EvaluationReviewReopen, or_(EvaluationReviewReopen.reviewer_id == user_id, EvaluationReviewReopen.created_by == user_id)),
    ]
    for label, model, condition in checks:
        count = count_rows(db, model, condition)
        if count:
            references.append(f"{label}{count}条")
    return references


def blocked_delete_error(name: str, references: list[str]) -> HTTPException:
    detail = "、".join(references)
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"{name}已被引用，不能删除。请先处理相关数据：{detail}。",
    )


def commit_or_integrity_error(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc


@router.get("/departments", response_model=list[DepartmentRow])
def list_departments(db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    return department_rows(db)


@router.get("/departments/choices", response_model=list[DepartmentChoice])
def list_department_choices(db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    return department_choice_rows(db)


@router.post("/departments", response_model=DepartmentRow, status_code=status.HTTP_201_CREATED)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    validate_department_parent(db, payload.parent_id)
    name = validate_department_name(db, payload.name, payload.parent_id)
    target_order = reserve_sort_order(db, Department, payload.sort_order) if payload.sort_order else next_sort_order(db, Department)
    department = Department(
        name=name,
        parent_id=payload.parent_id,
        sort_order=target_order,
    )
    db.add(department)
    commit_or_integrity_error(db, "同一上级部门下已存在同名部门。")
    return next(row for row in department_rows(db) if row["id"] == department.id)


@router.put("/departments/{department_id}", response_model=DepartmentRow)
def update_department(department_id: int, payload: DepartmentUpdate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    department = db.get(Department, department_id)
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在。")
    validate_department_parent(db, payload.parent_id, department_id)
    department.name = validate_department_name(db, payload.name, payload.parent_id, department_id)
    department.parent_id = payload.parent_id
    apply_sort_order(db, department, Department, payload.sort_order)
    commit_or_integrity_error(db, "同一上级部门下已存在同名部门。")
    return next(row for row in department_rows(db) if row["id"] == department.id)


@router.delete("/departments/{department_id}", response_model=MessageResponse)
def delete_department(department_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    department = db.get(Department, department_id)
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在。")
    references = department_delete_references(db, department_id)
    if references:
        raise blocked_delete_error("部门", references)
    db.delete(department)
    commit_or_integrity_error(db, "部门已被其他数据引用，不能删除。")
    return MessageResponse(message="部门已删除。")


@router.get("/positions", response_model=list[PositionRow])
def list_positions(db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    return position_rows(db)


@router.post("/positions", response_model=PositionRow, status_code=status.HTTP_201_CREATED)
def create_position(payload: PositionCreate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    target_order = reserve_sort_order(db, Position, payload.sort_order) if payload.sort_order else next_sort_order(db, Position)
    position = Position(name=payload.name.strip(), sort_order=target_order)
    db.add(position)
    commit_or_integrity_error(db, "职位名称已存在。")
    return {"id": position.id, "name": position.name, "sort_order": position.sort_order}


@router.put("/positions/{position_id}", response_model=PositionRow)
def update_position(position_id: int, payload: PositionUpdate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    position = db.get(Position, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="职位不存在。")
    position.name = payload.name.strip()
    apply_sort_order(db, position, Position, payload.sort_order)
    commit_or_integrity_error(db, "职位名称已存在。")
    return {"id": position.id, "name": position.name, "sort_order": position.sort_order}


@router.delete("/positions/{position_id}", response_model=MessageResponse)
def delete_position(position_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    position = db.get(Position, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="职位不存在。")
    references = position_delete_references(db, position_id)
    if references:
        raise blocked_delete_error("职位", references)
    db.delete(position)
    commit_or_integrity_error(db, "职位已被其他数据引用，不能删除。")
    return MessageResponse(message="职位已删除。")


@router.get("/positions/{position_id}/reviewer-users", response_model=list[ReviewerUserRow])
def reviewer_users_by_position(position_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    users = db.execute(
        select(User.id, User.full_name, Department.name.label("department_name"))
        .outerjoin(Department, User.department_id == Department.id)
        .where(User.role == "user", User.is_active.is_(True), User.position_id == position_id)
        .order_by(User.full_name, User.id)
    ).all()
    return [{"id": user.id, "name": user.full_name, "department_name": user.department_name} for user in users]


@router.get("/users", response_model=UserListResponse)
def list_users(q: str = "", page: int = 1, department_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    page_size = 10
    page = max(page, 1)
    users_stmt = (
        select(
            User.id,
            User.username,
            User.full_name,
            User.role,
            User.is_active,
            User.must_change_password,
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
    if department_id is not None:
        branch_ids = department_branch_ids(db, department_id)
        users_stmt = users_stmt.where(User.department_id.in_(branch_ids))
        count_stmt = count_stmt.where(User.department_id.in_(branch_ids))
    if q:
        like = f"%{q}%"
        filter_clause = User.username.like(like) | User.full_name.like(like)
        users_stmt = users_stmt.where(filter_clause)
        count_stmt = count_stmt.where(filter_clause)
    total = db.scalar(count_stmt) or 0
    page_info = pagination(total, page, page_size)
    user_rows = db.execute(users_stmt.offset((page_info.page - 1) * page_size).limit(page_size)).all()
    items = [
        {
            "id": row.id,
            "username": row.username,
            "full_name": row.full_name,
            "role": row.role,
            "is_active": row.is_active,
            "must_change_password": row.must_change_password,
            "department_id": row.department_id,
            "position_id": row.position_id,
            "department_name": row.department_name,
            "position_name": row.position_name,
        }
        for row in user_rows
    ]
    return UserListResponse(items=[UserRow(**item) for item in items], pagination=page_info)


@router.post("/users", response_model=UserRow, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    user = User(
        username=payload.username.strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password or "password!"),
        must_change_password=True,
        role=payload.role,
        department_id=payload.department_id,
        position_id=payload.position_id,
    )
    db.add(user)
    commit_or_integrity_error(db, "用户名已存在。")
    return UserRow(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        department_id=user.department_id,
        position_id=user.position_id,
    )


@router.put("/users/{target_id}", response_model=UserRow)
def update_user(target_id: int, payload: UserUpdate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    target = db.get(User, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="人员不存在。")
    revoke_sessions = bool(payload.password) or not payload.is_active or payload.role != target.role
    target.username = payload.username.strip()
    target.full_name = payload.full_name.strip()
    target.role = payload.role
    target.is_active = payload.is_active
    target.department_id = payload.department_id
    target.position_id = payload.position_id
    if payload.password:
        target.password_hash = hash_password(payload.password)
        target.must_change_password = True
    if revoke_sessions:
        db.execute(delete(UserSession).where(UserSession.user_id == target.id))
    commit_or_integrity_error(db, "用户名已存在。")
    department_name = target.department.name if target.department else None
    position_name = target.position.name if target.position else None
    return UserRow(
        id=target.id,
        username=target.username,
        full_name=target.full_name,
        role=target.role,
        is_active=target.is_active,
        must_change_password=target.must_change_password,
        department_id=target.department_id,
        position_id=target.position_id,
        department_name=department_name,
        position_name=position_name,
    )


@router.delete("/users/{target_id}", response_model=MessageResponse)
def delete_user(target_id: int, db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    target = db.get(User, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="人员不存在。")
    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能删除当前登录用户。")
    references = user_delete_references(db, target_id)
    if references:
        raise blocked_delete_error("人员", references)
    db.execute(delete(UserSession).where(UserSession.user_id == target.id))
    db.delete(target)
    commit_or_integrity_error(db, "人员已被其他数据引用，不能删除。")
    return MessageResponse(message="人员已删除。")


@router.get("/score-options", response_model=list[ScoreOptionRow])
def list_score_options(db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    return db.scalars(select(ScoreOption).order_by(ScoreOption.id)).all()


@router.post("/score-options", response_model=ScoreOptionRow, status_code=status.HTTP_201_CREATED)
def create_score_option(payload: ScoreOptionCreate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    option = ScoreOption(name=payload.name.strip(), value=Decimal(str(payload.value)))
    db.add(option)
    commit_or_integrity_error(db, "评分选项名称已存在。")
    return option


@router.put("/score-options/{option_id}", response_model=ScoreOptionRow)
def update_score_option(option_id: int, payload: ScoreOptionUpdate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    option = db.get(ScoreOption, option_id)
    if not option:
        raise HTTPException(status_code=404, detail="评分选项不存在。")
    option.name = payload.name.strip()
    option.value = Decimal(str(payload.value))
    commit_or_integrity_error(db, "评分选项名称已存在。")
    return option


@router.delete("/score-options/{option_id}", response_model=MessageResponse)
def delete_score_option(option_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)):
    option = db.get(ScoreOption, option_id)
    if not option:
        raise HTTPException(status_code=404, detail="评分选项不存在。")
    references = score_option_delete_references(db, option_id)
    if references:
        raise blocked_delete_error("评分选项", references)
    db.delete(option)
    commit_or_integrity_error(db, "评分选项已被其他数据引用，不能删除。")
    return MessageResponse(message="评分选项已删除。")
