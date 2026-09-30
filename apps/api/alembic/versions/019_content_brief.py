"""Remember the optional note on each content draft.

Revision ID: 019
Revises: 018
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "content_drafts" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("content_drafts")}
    if "brief" in existing:
        return
    op.add_column("content_drafts", sa.Column("brief", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    return
