"""Store the publication that an organic enquiry came from.

Revision ID: 036
Revises: 035

Downgrade is a no-op. It does not drop the new columns.
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "036"
down_revision = "035"
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
    creative = (
        sa.Column("publication_token", sa.String(64), server_default="", nullable=False),
        sa.Column("context_json", sa.Text(), server_default="", nullable=False),
    )
    for column in creative:
        _add_column_if_missing(inspector, "creative_versions", column)
    attribution = (
        sa.Column("creative_version_id", sa.Uuid(), nullable=True),
        sa.Column("operating_plan_id", sa.Uuid(), nullable=True),
        sa.Column("social_post_id", sa.Uuid(), nullable=True),
    )
    for table in ("leads", "inbound_captures"):
        for column in attribution:
            _add_column_if_missing(inspector, table, column)
    if bind.dialect.name != "postgresql":
        return
    bind.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))


def downgrade() -> None:
    return
