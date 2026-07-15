"""Repair evaluation batch columns for databases with a drifted revision."""

from alembic import op
import sqlalchemy as sa


revision = "20260715_05"
down_revision = "20260715_04"
branch_labels = None
depends_on = None


TABLE_NAME = "evaluations"
YEAR_INDEX = "ix_evaluations_year"
BATCH_CONSTRAINT = "uq_evaluations_year_sequence"
OPEN_CONSTRAINT = "uq_evaluations_single_open"
SQLITE_NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names() -> set[str]:
    return {column["name"] for column in _inspector().get_columns(TABLE_NAME)}


def _has_unique(column_names: list[str]) -> bool:
    inspector = _inspector()
    return any(
        constraint.get("column_names") == column_names
        for constraint in inspector.get_unique_constraints(TABLE_NAME)
    ) or any(
        index.get("unique") and index.get("column_names") == column_names
        for index in inspector.get_indexes(TABLE_NAME)
    )


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return

    columns = _column_names()
    if "sequence" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        )
    if "open_slot" not in columns:
        op.add_column(TABLE_NAME, sa.Column("open_slot", sa.Integer(), nullable=True))

    evaluations = sa.table(
        TABLE_NAME,
        sa.column("id", sa.Integer()),
        sa.column("year", sa.Integer()),
        sa.column("sequence", sa.Integer()),
        sa.column("is_open", sa.Boolean()),
        sa.column("open_slot", sa.Integer()),
    )
    open_ids = list(
        op.get_bind().scalars(
            sa.select(evaluations.c.id)
            .where(evaluations.c.is_open.is_(True))
            .order_by(
                evaluations.c.year.desc(),
                evaluations.c.sequence.desc(),
                evaluations.c.id.desc(),
            )
        )
    )
    op.execute(evaluations.update().values(open_slot=None))
    if open_ids:
        op.execute(
            evaluations.update()
            .where(evaluations.c.id != open_ids[0], evaluations.c.is_open.is_(True))
            .values(is_open=False)
        )
        op.execute(
            evaluations.update()
            .where(evaluations.c.id == open_ids[0])
            .values(open_slot=1)
        )

    if not _has_unique(["year", "sequence"]):
        rows = op.get_bind().execute(
            sa.select(
                evaluations.c.id,
                evaluations.c.year,
                evaluations.c.sequence,
            ).order_by(
                evaluations.c.year,
                evaluations.c.sequence,
                evaluations.c.id,
            )
        )
        next_sequence_by_year: dict[int, int] = {}
        for evaluation_id, year, _sequence in rows:
            next_sequence = next_sequence_by_year.get(year, 0) + 1
            next_sequence_by_year[year] = next_sequence
            op.execute(
                evaluations.update()
                .where(evaluations.c.id == evaluation_id)
                .values(sequence=next_sequence)
            )

    inspector = _inspector()
    for constraint in inspector.get_unique_constraints(TABLE_NAME):
        if constraint.get("column_names") != ["year"]:
            continue
        name = constraint.get("name")
        if name:
            with op.batch_alter_table(TABLE_NAME) as batch:
                batch.drop_constraint(name, type_="unique")
        elif op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(
                TABLE_NAME,
                naming_convention=SQLITE_NAMING_CONVENTION,
            ) as batch:
                batch.drop_constraint("uq_evaluations_year", type_="unique")

    for index in _inspector().get_indexes(TABLE_NAME):
        if index.get("unique") and index.get("column_names") == ["year"]:
            op.drop_index(index["name"], table_name=TABLE_NAME)

    if not _has_unique(["year", "sequence"]):
        with op.batch_alter_table(TABLE_NAME) as batch:
            batch.create_unique_constraint(BATCH_CONSTRAINT, ["year", "sequence"])
    if not _has_unique(["open_slot"]):
        with op.batch_alter_table(TABLE_NAME) as batch:
            batch.create_unique_constraint(OPEN_CONSTRAINT, ["open_slot"])

    if not any(
        index.get("column_names") == ["year"]
        for index in _inspector().get_indexes(TABLE_NAME)
    ):
        op.create_index(YEAR_INDEX, TABLE_NAME, ["year"], unique=False)


def downgrade() -> None:
    # This migration only repairs schema drift introduced before its revision.
    pass
