from datetime import datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import session_cookie_name
from app.database import get_db
from app.models import User, UserSession
from app.security import session_token_hash


def current_api_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(session_cookie_name())
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == session_token_hash(token)))
    if not session:
        return None
    if session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()
        return None
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        db.delete(session)
        db.commit()
        return None
    return user


def require_api_user(request: Request, user: User | None = Depends(current_api_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录。",
        )
    if (
        user.must_change_password
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.url.path != "/api/auth/change-password"
    ):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="首次登录或密码已被重置，请先修改密码。",
        )
    return user


def require_api_admin(user: User = Depends(require_api_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限。",
        )
    return user


def require_super_admin(user: User = Depends(require_api_admin)) -> User:
    if user.admin_scope_department_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员可以执行此操作。",
        )
    return user
