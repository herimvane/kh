import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "personnel_eval.db"


def normalize_database_url(url: str) -> str:
    value = url.strip()
    if value.startswith("mysql://"):
        value = value.replace("mysql://", "mysql+pymysql://", 1)
    elif value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)

    if value == "sqlite:///:memory:" or not value.startswith("sqlite:///"):
        return value
    path = value.removeprefix("sqlite:///")
    if Path(path).is_absolute():
        return value
    return f"sqlite:///{BASE_DIR / path}"


def database_url() -> str:
    configured = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH}")
    return normalize_database_url(configured)


def database_pool_size() -> int:
    return max(int(os.getenv("DB_POOL_SIZE", "5")), 1)


def database_max_overflow() -> int:
    return max(int(os.getenv("DB_MAX_OVERFLOW", "10")), 0)


def database_pool_recycle() -> int:
    return max(int(os.getenv("DB_POOL_RECYCLE", "1800")), 0)


def session_cookie_name() -> str:
    return os.getenv("SESSION_COOKIE_NAME", "personnel_session").strip() or "personnel_session"


def session_max_age() -> int:
    return max(int(os.getenv("SESSION_MAX_AGE", "28800")), 300)


def session_cookie_secure() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}


def score_detail_password_hash() -> str:
    return os.getenv("SCORE_DETAIL_PASSWORD_HASH", "").strip()


def log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"


def log_json() -> bool:
    return os.getenv("LOG_JSON", "true").strip().lower() in {"1", "true", "yes", "on"}
