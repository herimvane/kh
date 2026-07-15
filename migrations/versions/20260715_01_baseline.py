"""Establish a baseline for existing and new databases."""

from alembic import op
from app import models  # noqa: F401
from app.database import Base


revision = "20260715_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    # Adopt existing installations and create any tables absent from older releases.
    Base.metadata.create_all(bind=connection)


def downgrade() -> None:
    # The baseline deliberately never drops an adopted production database.
    pass
