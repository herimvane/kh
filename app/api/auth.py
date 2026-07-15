from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import require_api_user
from app.api.schemas import ChangePasswordRequest, LoginRequest, LoginResponse, MessageResponse, UserSummary
from app.config import session_cookie_name, session_cookie_secure, session_max_age
from app.database import get_db
from app.models import User, UserSession
from app.security import hash_password, new_session_token, session_token_hash, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        department_id=user.department_id,
        position_id=user.position_id,
    )


def role_home(user: User) -> str:
    return "/admin" if user.role == "admin" else "/app/evaluation"


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.username == payload.username, User.is_active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误。",
        )
    now = datetime.utcnow()
    db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    token = new_session_token()
    db.add(
        UserSession(
            token_hash=session_token_hash(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(seconds=session_max_age()),
        )
    )
    db.commit()
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=session_max_age(),
        httponly=True,
        secure=session_cookie_secure(),
        samesite="lax",
        path="/",
    )
    response.delete_cookie("user_id", path="/")
    return LoginResponse(user=user_summary(user), redirect_to=role_home(user))


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    token = request.cookies.get(session_cookie_name())
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == session_token_hash(token)))
        db.commit()
    response.delete_cookie(session_cookie_name(), path="/")
    response.delete_cookie("user_id", path="/")
    return MessageResponse(message="已退出登录。")


@router.get("/me", response_model=UserSummary)
def me(user: User = Depends(require_api_user)) -> UserSummary:
    return user_summary(user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(payload: ChangePasswordRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_api_user)) -> MessageResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确。")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="新密码至少需要 6 个字符。")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="新密码不能与当前密码相同。")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    current_token = request.cookies.get(session_cookie_name(), "")
    current_hash = session_token_hash(current_token) if current_token else ""
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.token_hash != current_hash,
        )
    )
    db.commit()
    return MessageResponse(message="密码修改成功。")
