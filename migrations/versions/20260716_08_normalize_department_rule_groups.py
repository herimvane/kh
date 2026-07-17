"""Normalize legacy department rules into logical groups."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260716_08"
down_revision = "20260716_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "evaluation_department_rules" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("evaluation_department_rules")}
    if "group_key" not in columns:
        return

    rows = bind.execute(
        sa.text(
            "SELECT id, evaluation_id, reviewer_position_id, weight "
            "FROM evaluation_department_rules ORDER BY id"
        )
    ).mappings().all()
    group_keys: dict[tuple[int, int, str], str] = {}
    for row in rows:
        signature = (
            int(row["evaluation_id"]),
            int(row["reviewer_position_id"]),
            str(row["weight"]),
        )
        group_key = group_keys.setdefault(signature, str(uuid4()))
        bind.execute(
            sa.text(
                "UPDATE evaluation_department_rules "
                "SET group_key = :group_key WHERE id = :rule_id"
            ),
            {"group_key": group_key, "rule_id": row["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "evaluation_department_rules" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("evaluation_department_rules")}
    if "group_key" not in columns:
        return
    rule_ids = bind.execute(sa.text("SELECT id FROM evaluation_department_rules")).scalars().all()
    for rule_id in rule_ids:
        bind.execute(
            sa.text(
                "UPDATE evaluation_department_rules "
                "SET group_key = :group_key WHERE id = :rule_id"
            ),
            {"group_key": str(uuid4()), "rule_id": rule_id},
        )
