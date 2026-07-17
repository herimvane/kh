"""Store archived reviewer department scope."""

from alembic import op
import sqlalchemy as sa


revision = "20260716_09"
down_revision = "20260716_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "archived_submissions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("archived_submissions")}
    if "reviewer_department_id" not in columns:
        op.add_column(
            "archived_submissions",
            sa.Column("reviewer_department_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_archived_submissions_reviewer_department_id",
            "archived_submissions",
            ["reviewer_department_id"],
        )

    bind.execute(
        sa.text(
            "UPDATE archived_submissions "
            "SET reviewer_department_id = ("
            "SELECT users.department_id FROM users "
            "WHERE users.id = archived_submissions.reviewer_id"
            ") WHERE reviewer_department_id IS NULL"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "archived_submissions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("archived_submissions")}
    if "reviewer_department_id" not in columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes("archived_submissions")}
    if "ix_archived_submissions_reviewer_department_id" in indexes:
        op.drop_index("ix_archived_submissions_reviewer_department_id", table_name="archived_submissions")
    op.drop_column("archived_submissions", "reviewer_department_id")
