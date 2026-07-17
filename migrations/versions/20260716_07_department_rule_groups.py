"""Group multi-department evaluation rules."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260716_07"
down_revision = "20260715_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "evaluation_department_rules" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("evaluation_department_rules")}
    if "group_key" not in columns:
        with op.batch_alter_table("evaluation_department_rules") as batch:
            batch.add_column(sa.Column("group_key", sa.String(36), nullable=True))

    rule_ids = bind.execute(sa.text("SELECT id FROM evaluation_department_rules")).scalars().all()
    for rule_id in rule_ids:
        bind.execute(
            sa.text("UPDATE evaluation_department_rules SET group_key = :group_key WHERE id = :rule_id"),
            {"group_key": str(uuid4()), "rule_id": rule_id},
        )

    with op.batch_alter_table("evaluation_department_rules") as batch:
        batch.alter_column("group_key", existing_type=sa.String(36), nullable=False)
    if not any(index.get("name") == "ix_evaluation_department_rules_group_key" for index in sa.inspect(bind).get_indexes("evaluation_department_rules")):
        op.create_index(
            "ix_evaluation_department_rules_group_key",
            "evaluation_department_rules",
            ["group_key"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "evaluation_department_rules" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("evaluation_department_rules")}
    if "group_key" in columns:
        with op.batch_alter_table("evaluation_department_rules") as batch:
            batch.drop_index("ix_evaluation_department_rules_group_key")
            batch.drop_column("group_key")
