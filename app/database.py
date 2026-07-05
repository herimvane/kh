import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "personnel_eval.db"
RAW_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH}")


def normalize_database_url(url: str) -> str:
    if url == "sqlite:///:memory:" or not url.startswith("sqlite:///"):
        return url
    path = url.removeprefix("sqlite:///")
    if Path(path).is_absolute():
        return url
    return f"sqlite:///{BASE_DIR / path}"


DATABASE_URL = normalize_database_url(RAW_DATABASE_URL)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = {"connect_args": connect_args}
if DATABASE_URL == "sqlite:///:memory:":
    engine_kwargs["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_initialized = False


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    global _initialized

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            def ensure_column(table: str, column: str, definition: str) -> None:
                columns = {
                    row[1]
                    for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                }
                if column not in columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))

            ensure_column("departments", "sort_order", "INTEGER NOT NULL DEFAULT 0")
            ensure_column("positions", "sort_order", "INTEGER NOT NULL DEFAULT 0")
            ensure_column("evaluations", "name", "VARCHAR(160) NOT NULL DEFAULT ''")
            ensure_column(
                "evaluation_person_rules",
                "scope_type",
                "VARCHAR(40) NOT NULL DEFAULT 'selected_departments'",
            )
            ensure_column("evaluation_person_rules", "reviewer_user_id", "INTEGER")
            ensure_column("evaluation_person_rules", "score_group", "VARCHAR(160) NOT NULL DEFAULT ''")
            for table in ("departments", "positions"):
                conn.execute(
                    text(
                        f"UPDATE {table} SET sort_order = id "
                        "WHERE sort_order IS NULL OR sort_order = 0"
                    )
                )
            conn.execute(
                text(
                    "UPDATE evaluations SET name = CAST(year AS TEXT) || ' 年考核' "
                    "WHERE name IS NULL OR name = ''"
                )
            )
    _initialized = True


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
