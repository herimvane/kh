"""Add hierarchical administrator scopes and concurrent evaluation scopes."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260715_06"
down_revision = "20260715_05"
branch_labels = None
depends_on = None


SQLITE_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _drop_unique(table_name: str, columns: list[str]) -> None:
    inspector = _inspector()
    for constraint in inspector.get_unique_constraints(table_name):
        if constraint.get("column_names") != columns:
            continue
        name = constraint.get("name")
        if name:
            with op.batch_alter_table(table_name) as batch:
                batch.drop_constraint(name, type_="unique")
        elif op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(
                table_name,
                naming_convention=SQLITE_NAMING_CONVENTION,
            ) as batch:
                batch.drop_constraint(
                    f"uq_{table_name}_{columns[0]}",
                    type_="unique",
                )
    for index in _inspector().get_indexes(table_name):
        if index.get("unique") and index.get("column_names") == columns:
            op.drop_index(index["name"], table_name=table_name)


def _has_unique(table_name: str, columns: list[str]) -> bool:
    inspector = _inspector()
    return any(
        item.get("column_names") == columns
        for item in inspector.get_unique_constraints(table_name)
    ) or any(
        item.get("unique") and item.get("column_names") == columns
        for item in inspector.get_indexes(table_name)
    )


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if any(index.get("name") == index_name for index in _inspector().get_indexes(table_name)):
        return
    op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    table_names = set(_inspector().get_table_names())

    if "users" in table_names:
        user_columns = _columns("users")
        with op.batch_alter_table("users") as batch:
            if "identity_key" not in user_columns:
                batch.add_column(sa.Column("identity_key", sa.String(36), nullable=True))
            if "admin_scope_department_id" not in user_columns:
                batch.add_column(sa.Column("admin_scope_department_id", sa.Integer(), nullable=True))
                if "departments" in table_names:
                    batch.create_foreign_key(
                        "fk_users_admin_scope_department_id_departments",
                        "departments",
                        ["admin_scope_department_id"],
                        ["id"],
                    )

        users = sa.table(
            "users",
            sa.column("id", sa.Integer()),
            sa.column("identity_key", sa.String(36)),
        )
        for user_id, identity_key in op.get_bind().execute(
            sa.select(users.c.id, users.c.identity_key)
        ):
            if not identity_key:
                op.execute(
                    users.update()
                    .where(users.c.id == user_id)
                    .values(identity_key=str(uuid4()))
                )
        if not _has_unique("users", ["identity_key"]):
            with op.batch_alter_table("users") as batch:
                batch.alter_column("identity_key", existing_type=sa.String(36), nullable=False)
                batch.create_unique_constraint("uq_users_identity_key", ["identity_key"])
        _create_index_if_missing("users", "ix_users_admin_scope_department_id", ["admin_scope_department_id"])

    if "evaluations" in table_names:
        evaluation_columns = _columns("evaluations")
        with op.batch_alter_table("evaluations") as batch:
            if "scope_key" not in evaluation_columns:
                batch.add_column(sa.Column("scope_key", sa.String(64), nullable=False, server_default="GLOBAL"))
            if "owner_department_id" not in evaluation_columns:
                batch.add_column(sa.Column("owner_department_id", sa.Integer(), nullable=True))
                if "departments" in table_names:
                    batch.create_foreign_key(
                        "fk_evaluations_owner_department_id_departments",
                        "departments",
                        ["owner_department_id"],
                        ["id"],
                        ondelete="SET NULL",
                    )
            if "owner_department_name_snapshot" not in evaluation_columns:
                batch.add_column(sa.Column("owner_department_name_snapshot", sa.String(120), nullable=False, server_default="全局"))
            if "created_by_id" not in evaluation_columns:
                batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
                if "users" in table_names:
                    batch.create_foreign_key(
                        "fk_evaluations_created_by_id_users",
                        "users",
                        ["created_by_id"],
                        ["id"],
                        ondelete="SET NULL",
                    )

        _drop_unique("evaluations", ["year", "sequence"])
        _drop_unique("evaluations", ["open_slot"])
        if not _has_unique("evaluations", ["scope_key", "year", "sequence"]):
            with op.batch_alter_table("evaluations") as batch:
                batch.create_unique_constraint(
                    "uq_evaluations_scope_year_sequence",
                    ["scope_key", "year", "sequence"],
                )
        if not _has_unique("evaluations", ["scope_key", "open_slot"]):
            with op.batch_alter_table("evaluations") as batch:
                batch.create_unique_constraint(
                    "uq_evaluations_scope_open",
                    ["scope_key", "open_slot"],
                )
        _create_index_if_missing("evaluations", "ix_evaluations_scope_key", ["scope_key"])
        _create_index_if_missing("evaluations", "ix_evaluations_owner_department_id", ["owner_department_id"])

    identity_by_id = {}
    if "users" in table_names:
        users = sa.table(
            "users",
            sa.column("id", sa.Integer()),
            sa.column("identity_key", sa.String(36)),
        )
        identity_by_id = dict(
            op.get_bind().execute(sa.select(users.c.id, users.c.identity_key)).all()
        )
    for table_name in ("archived_submissions", "archived_vote_details"):
        if table_name not in table_names:
            continue
        columns = _columns(table_name)
        if "reviewer_identity_key" not in columns:
            op.add_column(
                table_name,
                sa.Column("reviewer_identity_key", sa.String(64), nullable=False, server_default=""),
            )
        archive_table = sa.table(
            table_name,
            sa.column("id", sa.Integer()),
            sa.column("reviewer_id", sa.Integer()),
            sa.column("reviewer_identity_key", sa.String(64)),
        )
        for row_id, reviewer_id, identity_key in op.get_bind().execute(
            sa.select(
                archive_table.c.id,
                archive_table.c.reviewer_id,
                archive_table.c.reviewer_identity_key,
            )
        ):
            if not identity_key:
                op.execute(
                    archive_table.update()
                    .where(archive_table.c.id == row_id)
                    .values(
                        reviewer_identity_key=identity_by_id.get(
                            reviewer_id,
                            f"legacy-user-{reviewer_id}",
                        )
                    )
                )
        if table_name == "archived_submissions":
            _create_index_if_missing(
                table_name,
                "ix_archived_submissions_reviewer_identity_key",
                ["reviewer_identity_key"],
            )


def downgrade() -> None:
    raise RuntimeError("管理员权限域迁移包含身份快照，不能自动安全回滚。")
