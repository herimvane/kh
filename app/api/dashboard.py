from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin_scope import manageable_department_ids
from app.api.deps import require_api_admin
from app.api.evaluation_helpers import evaluation_row
from app.database import get_db
from app.models import Department, Evaluation, User


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(require_api_admin)):
    allowed = manageable_department_ids(db, user)

    user_stmt = select(func.count(User.id)).where(User.role == "user", User.is_active.is_(True))
    evaluation_stmt = select(Evaluation)
    if allowed is None:
        department_total = db.scalar(select(func.count(Department.id))) or 0
    else:
        department_total = len(allowed)
        user_stmt = user_stmt.where(User.department_id.in_(allowed))
        evaluation_stmt = evaluation_stmt.where(Evaluation.owner_department_id.in_(allowed))

    evaluations = db.scalars(
        evaluation_stmt.order_by(
            Evaluation.year.desc(),
            Evaluation.sequence.desc(),
            Evaluation.created_at.desc(),
            Evaluation.id.desc(),
        )
    ).all()
    rows = [evaluation_row(db, evaluation) for evaluation in evaluations]
    total_tasks = sum(row.total_tasks for row in rows)
    submitted_tasks = sum(row.submitted_tasks for row in rows)
    current_year = datetime.utcnow().year
    return {
        "user_total": db.scalar(user_stmt) or 0,
        "department_total": department_total,
        "evaluation_total": len(rows),
        "current_year_total": sum(row.year == current_year for row in rows),
        "active_total": sum(row.is_open and not row.archived for row in rows),
        "completed_total": sum(row.archived or (row.total_tasks > 0 and row.submitted_tasks >= row.total_tasks) for row in rows),
        "total_tasks": total_tasks,
        "submitted_tasks": submitted_tasks,
        "latest": rows[:5],
    }
