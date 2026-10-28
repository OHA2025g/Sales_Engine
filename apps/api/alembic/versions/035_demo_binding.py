"""Bind a demonstration to its creative, page, form, and action budget.

Revision ID: 035
Revises: 034

Downgrade is a no-op. It does not drop the new columns.
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "035"
down_revision = "034"
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
    columns = (
        sa.Column("content_hash", sa.String(64), server_default="", nullable=False),
        sa.Column("form_url", sa.Text(), server_default="", nullable=False),
        sa.Column("page_ref", sa.String(200), server_default="", nullable=False),
        sa.Column("page_name", sa.String(200), server_default="", nullable=False),
        sa.Column("calendar_id", sa.String(255), server_default="", nullable=False),
        sa.Column("allowed_actions", sa.Text(), server_default="", nullable=False),
        sa.Column("binding_digest", sa.String(64), server_default="", nullable=False),
    )
    for column in columns:
        _add_column_if_missing(inspector, "demo_scopes", column)
    if bind.dialect.name != "postgresql":
        return
    bind.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))


def downgrade() -> None:
    return
