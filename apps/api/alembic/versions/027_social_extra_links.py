"""Store extra links written into a social post beside the form link.

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "social_posts" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("social_posts")}
    if "extra_links" in existing:
        return
    op.add_column("social_posts", sa.Column("extra_links", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    return
