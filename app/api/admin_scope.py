from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, Evaluation, User


def is_super_admin(user: User) -> bool:
    return user.role == "admin" and user.admin_scope_department_id is None


def department_branch_ids(db: Session, department_id: int) -> set[int]:
    if not db.get(Department, department_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="管理员管理范围部门不存在。")
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


def manageable_department_ids(db: Session, user: User) -> set[int] | None:
    if is_super_admin(user):
        return None
    if user.role != "admin" or user.admin_scope_department_id is None:
        return set()
    return department_branch_ids(db, user.admin_scope_department_id)


def ensure_departments_manageable(db: Session, user: User, department_ids: list[int] | set[int]) -> None:
    allowed = manageable_department_ids(db, user)
    if allowed is not None and not set(department_ids).issubset(allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="所选部门超出当前管理员的数据范围。")


def ensure_department_manageable(
    db: Session,
    user: User,
    department_id: int | None,
    detail: str = "无权查看或管理该评分人的提交记录。",
) -> None:
    allowed = manageable_department_ids(db, user)
    if allowed is not None and (department_id is None or department_id not in allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def can_access_evaluation(db: Session, user: User, evaluation: Evaluation) -> bool:
    if is_super_admin(user):
        return True
    allowed = manageable_department_ids(db, user)
    return evaluation.owner_department_id is not None and evaluation.owner_department_id in (allowed or set())


def evaluation_scope_values(db: Session, user: User, requested_department_id: int | None) -> tuple[str, int | None, str]:
    if is_super_admin(user):
        owner_id = requested_department_id
    else:
        owner_id = user.admin_scope_department_id
    if owner_id is None:
        return "GLOBAL", None, "全局"
    ensure_departments_manageable(db, user, [owner_id])
    department = db.get(Department, owner_id)
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="考核所属部门不存在。")
    return f"DEPT:{owner_id}", owner_id, department.name
