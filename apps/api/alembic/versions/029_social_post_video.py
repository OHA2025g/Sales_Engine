"""Store a short video on a social post.

Revision ID: 029
Revises: 028
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "social_posts" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("social_posts")}
    if "video_url" in existing:
        return
    op.add_column("social_posts", sa.Column("video_url", sa.String(length=500), nullable=False, server_default=""))


def downgrade() -> None:
    return
