from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import (
    database_max_overflow,
    database_pool_recycle,
    database_pool_size,
    database_url,
    normalize_database_url,
)

DATABASE_URL = database_url()
DATABASE_BACKEND = make_url(DATABASE_URL).get_backend_name()


def engine_options(url: str) -> dict:
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    options: dict = {}
    if backend == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        if parsed.database == ":memory:":
            options["poolclass"] = StaticPool
        return options

    options.update(
        pool_pre_ping=True,
        pool_size=database_pool_size(),
        max_overflow=database_max_overflow(),
        pool_recycle=database_pool_recycle(),
    )
    if backend == "mysql":
        options["connect_args"] = {"charset": "utf8mb4"}
    return options


engine_kwargs = engine_options(DATABASE_URL)
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_initialized = False


class Base(DeclarativeBase):
    pass


def migrate_db() -> None:
    if DATABASE_URL == "sqlite:///:memory:":
        return
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        _validate_migrated_schema(connection)


def _validate_migrated_schema(connection) -> None:
    inspector = inspect(connection)
    if "evaluations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("evaluations")}
    missing = {"sequence", "open_slot"} - columns
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeError(
            "数据库迁移版本与实际表结构不一致：evaluations 表缺少字段 "
            f"{names}。请确认 migrations 目录完整后重新执行 alembic upgrade head。"
        )


def init_db() -> None:
    global _initialized

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _initialized = True


def database_display_url() -> str:
    return make_url(DATABASE_URL).render_as_string(hide_password=True)


def check_database_connection() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db():
    if not _initialized:
        init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
