"""Assign a lead to a workspace user.

Revision ID: 030
Revises: 029
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "leads" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("leads")}
    if "owner_id" in existing:
        return
    op.add_column("leads", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index("ix_leads_owner_id", "leads", ["owner_id"])
    op.create_foreign_key("fk_leads_owner_id_users", "leads", "users", ["owner_id"], ["id"])


def downgrade() -> None:
    return
