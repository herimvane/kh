from pathlib import Path

from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.config import BASE_DIR, normalize_database_url
from app.database import Base, engine_options
from app import models  # noqa: F401


def test_database_url_aliases_and_relative_sqlite_path():
    assert normalize_database_url("mysql://user:pass@localhost/app") == "mysql+pymysql://user:pass@localhost/app"
    assert normalize_database_url("postgres://user:pass@localhost/app") == "postgresql+psycopg://user:pass@localhost/app"
    assert normalize_database_url("postgresql://user:pass@localhost/app") == "postgresql+psycopg://user:pass@localhost/app"
    assert normalize_database_url("sqlite:///data/test.db") == f"sqlite:///{BASE_DIR / Path('data/test.db')}"
    assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_engine_options_are_backend_specific():
    assert engine_options("sqlite:///:memory:")["connect_args"]["check_same_thread"] is False
    assert "pool_pre_ping" not in engine_options("sqlite:///test.db")
    assert engine_options("mysql+pymysql://user:pass@localhost/app")["connect_args"] == {"charset": "utf8mb4"}
    assert engine_options("postgresql+psycopg://user:pass@localhost/app")["pool_pre_ping"] is True


def test_schema_compiles_for_all_supported_databases():
    dialects = (sqlite.dialect(), mysql.dialect(), postgresql.dialect())
    for dialect in dialects:
        for table in Base.metadata.sorted_tables:
            compiled = str(CreateTable(table).compile(dialect=dialect))
            assert f"CREATE TABLE {table.name}" in compiled
