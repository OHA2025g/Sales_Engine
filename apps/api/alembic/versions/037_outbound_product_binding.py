"""Bind a sequence enrollment to the product context used for its drafts.

Revision ID: 037
Revises: 036

Downgrade is a no-op. It does not drop the new columns.
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector, table: str, column: sa.Column) -> None:
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    if column.name in existing:
        return
    op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    inspector = inspect(bind)
    _add_column_if_missing(inspector, "sequences", sa.Column("operating_plan_id", sa.Uuid(), nullable=True))
    _add_column_if_missing(inspector, "sequence_enrollments", sa.Column("context_json", sa.Text(), server_default="", nullable=False))
    _add_column_if_missing(
        inspector,
        "sequence_enrollments",
        sa.Column("context_version", sa.String(length=64), server_default="", nullable=False),
    )
    _add_column_if_missing(
        inspector,
        "assessment_decisions",
        sa.Column("outbound_eligible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    if bind.dialect.name != "postgresql":
        return
    bind.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))


def downgrade() -> None:
    return
