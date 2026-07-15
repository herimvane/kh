"""Add forced password changes and use fixed precision scores."""

from alembic import op
import sqlalchemy as sa


revision = "20260715_02"
down_revision = "20260715_01"
branch_labels = None
depends_on = None


NUMERIC_COLUMNS = {
    "departments": ("score_note",),
    "score_options": ("value",),
    "evaluation_person_rules": ("weight",),
    "evaluation_department_rules": ("weight",),
    "evaluation_department_share_rules": ("weight", "manual_department_score"),
    "evaluation_department_score_share_rules": ("weight",),
    "evaluation_department_manual_scores": ("score",),
    "evaluation_tasks": ("weight",),
    "evaluation_votes": ("score_value",),
    "archived_person_scores": ("final_score",),
    "archived_department_scores": ("final_score",),
    "archived_vote_details": ("score_value", "weight", "weighted_score"),
}


def columns_for(table_name: str):
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    user_columns = columns_for("users")
    if "must_change_password" not in user_columns:
        op.add_column(
            "users",
            sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    for table_name, column_names in NUMERIC_COLUMNS.items():
        table_columns = columns_for(table_name)
        with op.batch_alter_table(table_name) as batch:
            for column_name in column_names:
                if column_name not in table_columns:
                    continue
                column = table_columns[column_name]
                if not isinstance(column["type"], sa.Numeric) or getattr(column["type"], "scale", None) != 4:
                    batch.alter_column(
                        column_name,
                        existing_type=column["type"],
                        type_=sa.Numeric(12, 4),
                        existing_nullable=column["nullable"],
                    )


def downgrade() -> None:
    for table_name, column_names in reversed(tuple(NUMERIC_COLUMNS.items())):
        table_columns = columns_for(table_name)
        with op.batch_alter_table(table_name) as batch:
            for column_name in column_names:
                if column_name not in table_columns:
                    continue
                column = table_columns[column_name]
                batch.alter_column(
                    column_name,
                    existing_type=column["type"],
                    type_=sa.Float(),
                    existing_nullable=column["nullable"],
                )
    if "must_change_password" in columns_for("users"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("must_change_password")
