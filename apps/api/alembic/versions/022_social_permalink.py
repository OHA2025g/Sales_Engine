"""Store the public URL of a published social post.

Revision ID: 022
Revises: 021
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "022"
down_revision = "021"
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
    inspector = inspect(op.get_bind())
    _add_column_if_missing(inspector, "social_posts", sa.Column("permalink", sa.String(500), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "content_drafts", sa.Column("permalink", sa.String(500), nullable=False, server_default=""))


def downgrade() -> None:
    return
