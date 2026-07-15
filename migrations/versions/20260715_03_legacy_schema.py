"""Converge legacy databases that predate versioned migrations."""

from alembic import op
import sqlalchemy as sa


revision = "20260715_03"
down_revision = "20260715_02"
branch_labels = None
depends_on = None


LEGACY_COLUMNS = {
    "departments": (
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    ),
    "positions": (
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    ),
    "evaluations": (
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
    ),
    "evaluation_person_rules": (
        sa.Column("scope_type", sa.String(length=40), nullable=False, server_default="selected_departments"),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("score_group", sa.String(length=160), nullable=False, server_default=""),
    ),
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())
    for table_name, definitions in LEGACY_COLUMNS.items():
        if table_name not in table_names:
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for definition in definitions:
            if definition.name not in existing:
                op.add_column(table_name, definition)

    departments = sa.table("departments", sa.column("id"), sa.column("sort_order"))
    positions = sa.table("positions", sa.column("id"), sa.column("sort_order"))
    evaluations = sa.table("evaluations", sa.column("year"), sa.column("name"))
    for table in (departments, positions):
        op.execute(table.update().where(sa.or_(table.c.sort_order.is_(None), table.c.sort_order == 0)).values(sort_order=table.c.id))
    op.execute(
        evaluations.update()
        .where(sa.or_(evaluations.c.name.is_(None), evaluations.c.name == ""))
        .values(name=sa.cast(evaluations.c.year, sa.String()) + sa.literal(" 年考核"))
    )


def downgrade() -> None:
    # Legacy convergence is intentionally non-destructive.
    pass
