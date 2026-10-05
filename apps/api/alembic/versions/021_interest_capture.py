"""Interest form fields for inbound captures.

Revision ID: 021
Revises: 020
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "021"
down_revision = "020"
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
    _add_column_if_missing(inspector, "inbound_captures", sa.Column("phone", sa.String(40), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "inbound_captures", sa.Column("request_note", sa.Text(), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "public_form_keys", sa.Column("token_encrypted", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    return
