"""Remember which public form a social post links to.

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "social_posts" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("social_posts")}
    if "form_key_id" in existing:
        return
    op.add_column("social_posts", sa.Column("form_key_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    return
