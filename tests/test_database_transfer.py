from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Department, User, UserSession
from app.security import hash_password
from scripts.database_transfer import collect_backup, read_backup, restore_backup, write_backup


def sqlite_engine(path: Path):
    return create_engine(f"sqlite:///{path}")


def test_logical_backup_restores_data_and_revokes_sessions(tmp_path):
    source = sqlite_engine(tmp_path / "source.db")
    target = sqlite_engine(tmp_path / "target.db")
    Base.metadata.create_all(source)
    with Session(source) as db:
        department = Department(name="办公室", sort_order=1)
        db.add(department)
        db.flush()
        user = User(username="user1", full_name="测试用户", password_hash=hash_password("secret"), department_id=department.id)
        db.add(user)
        db.flush()
        db.add(UserSession(token_hash="a" * 64, user_id=user.id, expires_at=datetime.utcnow()))
        db.commit()

    backup_path = tmp_path / "backup.json.gz"
    payload = collect_backup(source)
    write_backup(payload, backup_path)
    restored_payload = read_backup(backup_path)
    imported = restore_backup(target, restored_payload)

    with Session(target) as db:
        assert db.scalar(select(Department).where(Department.name == "办公室"))
        assert db.scalar(select(User).where(User.username == "user1"))
        assert db.scalar(select(UserSession)) is None
    assert imported > 0


def test_restore_refuses_to_overwrite_nonempty_database(tmp_path):
    source = sqlite_engine(tmp_path / "source.db")
    target = sqlite_engine(tmp_path / "target.db")
    Base.metadata.create_all(source)
    Base.metadata.create_all(target)
    with Session(source) as db:
        db.add(Department(name="源部门", sort_order=1))
        db.commit()
    with Session(target) as db:
        db.add(Department(name="目标部门", sort_order=1))
        db.commit()

    payload = collect_backup(source)
    try:
        restore_backup(target, payload)
    except RuntimeError as error:
        assert "--clear-existing" in str(error)
    else:
        raise AssertionError("非空目标数据库应拒绝无确认的覆盖。")

    restored = restore_backup(target, payload, clear_existing=True)
    with Session(target) as db:
        assert db.scalar(select(Department).where(Department.name == "源部门"))
        assert db.scalar(select(Department).where(Department.name == "目标部门")) is None
    assert restored > 0
