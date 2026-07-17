from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parent.parent


def test_fresh_database_upgrades_to_head(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    with engine.begin() as connection:
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260716_09"
        evaluation_columns = {column["name"] for column in inspect(connection).get_columns("evaluations")}
        user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
        assert {"scope_key", "owner_department_id", "created_by_id"} <= evaluation_columns
        assert {"identity_key", "admin_scope_department_id"} <= user_columns
        department_rule_columns = {column["name"] for column in inspect(connection).get_columns("evaluation_department_rules")}
        assert "group_key" in department_rule_columns
        archived_submission_columns = {column["name"] for column in inspect(connection).get_columns("archived_submissions")}
        assert "reviewer_department_id" in archived_submission_columns


def test_evaluation_batch_migration_repairs_drifted_revision(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'drifted.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE evaluations (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(160) NOT NULL,
                    year INTEGER NOT NULL UNIQUE,
                    is_open BOOLEAN NOT NULL DEFAULT 0,
                    tasks_generated BOOLEAN NOT NULL DEFAULT 0,
                    archived BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluations (id, name, year, is_open) "
                "VALUES (1, '2026 年考核', 2026, 1)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('20260715_04')")
        )

        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        columns = {column["name"] for column in inspect(connection).get_columns("evaluations")}
        assert {"sequence", "open_slot", "scope_key", "owner_department_id", "created_by_id"} <= columns
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260716_09"
        assert connection.execute(
            text("SELECT sequence, open_slot FROM evaluations WHERE id = 1")
        ).one() == (1, 1)

        connection.execute(
            text(
                """
                INSERT INTO evaluations (
                    id, name, year, sequence, is_open, tasks_generated, archived
                ) VALUES (2, '2026-02', 2026, 2, 0, 0, 0)
                """
            )
        )
