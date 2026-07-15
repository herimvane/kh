"""Allow multiple evaluation batches in the same year."""

from alembic import op
import sqlalchemy as sa


revision = "20260715_04"
down_revision = "20260715_03"
branch_labels = None
depends_on = None


TABLE_NAME = "evaluations"
YEAR_INDEX = "ix_evaluations_year"
BATCH_CONSTRAINT = "uq_evaluations_year_sequence"
OPEN_CONSTRAINT = "uq_evaluations_single_open"
SQLITE_NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
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
    open_ids = [
        row[0]
        for row in op.get_bind().execute(
            sa.select(evaluations.c.id)
            .where(evaluations.c.is_open.is_(True))
            .order_by(evaluations.c.year.desc(), evaluations.c.sequence.desc(), evaluations.c.id.desc())
        )
    ]
    op.execute(evaluations.update().values(open_slot=None))
    if open_ids:
        op.execute(
            evaluations.update()
            .where(evaluations.c.id != open_ids[0], evaluations.c.is_open.is_(True))
            .values(is_open=False)
        )
        op.execute(evaluations.update().where(evaluations.c.id == open_ids[0]).values(open_slot=1))

    inspector = _inspector()
    unique_constraints = inspector.get_unique_constraints(TABLE_NAME)
    for constraint in unique_constraints:
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

    inspector = _inspector()
    indexes = inspector.get_indexes(TABLE_NAME)
    unique_constraints = inspector.get_unique_constraints(TABLE_NAME)
    has_batch_constraint = any(
        constraint.get("column_names") == ["year", "sequence"]
        for constraint in unique_constraints
    ) or any(
        index.get("unique") and index.get("column_names") == ["year", "sequence"]
        for index in indexes
    )
    if not has_batch_constraint:
        with op.batch_alter_table(TABLE_NAME) as batch:
            batch.create_unique_constraint(BATCH_CONSTRAINT, ["year", "sequence"])

    inspector = _inspector()
    has_open_constraint = any(
        constraint.get("column_names") == ["open_slot"]
        for constraint in inspector.get_unique_constraints(TABLE_NAME)
    ) or any(
        index.get("unique") and index.get("column_names") == ["open_slot"]
        for index in inspector.get_indexes(TABLE_NAME)
    )
    if not has_open_constraint:
        with op.batch_alter_table(TABLE_NAME) as batch:
            batch.create_unique_constraint(OPEN_CONSTRAINT, ["open_slot"])

    inspector = _inspector()
    if not any(index.get("column_names") == ["year"] for index in inspector.get_indexes(TABLE_NAME)):
        op.create_index(YEAR_INDEX, TABLE_NAME, ["year"], unique=False)


def downgrade() -> None:
    duplicate_year = op.get_bind().execute(
        sa.text(
            "SELECT year FROM evaluations GROUP BY year HAVING COUNT(*) > 1"
        )
    ).first()
    if duplicate_year:
        raise RuntimeError("存在同年度多批次考核，无法安全回滚到年度唯一结构。")

    inspector = _inspector()
    if any(index.get("name") == YEAR_INDEX for index in inspector.get_indexes(TABLE_NAME)):
        op.drop_index(YEAR_INDEX, table_name=TABLE_NAME)
    with op.batch_alter_table(TABLE_NAME) as batch:
        constraints = {item.get("name") for item in inspector.get_unique_constraints(TABLE_NAME)}
        if OPEN_CONSTRAINT in constraints:
            batch.drop_constraint(OPEN_CONSTRAINT, type_="unique")
        if BATCH_CONSTRAINT in constraints:
            batch.drop_constraint(BATCH_CONSTRAINT, type_="unique")
        batch.drop_column("open_slot")
        batch.drop_column("sequence")
    op.create_index(YEAR_INDEX, TABLE_NAME, ["year"], unique=True)
