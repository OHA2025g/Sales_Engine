"""Store the fields a public form shows.

Revision ID: 028
Revises: 027
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "public_form_keys" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("public_form_keys")}
    if "schema_json" in existing:
        return
    op.add_column("public_form_keys", sa.Column("schema_json", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    return
