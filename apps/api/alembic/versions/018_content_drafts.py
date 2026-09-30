"""Seller profile, product description, and content drafts.

Revision ID: 018
Revises: 017
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector, table: str, column: sa.Column) -> None:
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    if column.name in existing:
        return
    op.add_column(table, column)


def _enable_rls(conn, table: str, using_sql: str) -> None:
    conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    conn.execute(text(f'CREATE POLICY tenant_isolation ON "{table}" USING ({using_sql}) WITH CHECK ({using_sql})'))


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    inspector = inspect(bind)
    _add_column_if_missing(inspector, "products", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    if bind.dialect.name != "postgresql":
        return
    conn = bind
    conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))
    using = "tenant_id::text = current_setting('app.current_tenant_id', true)"
    names = inspect(bind).get_table_names()
    for table in ("seller_profiles", "content_drafts"):
        if table in names:
            _enable_rls(conn, table, using)


def downgrade() -> None:
    return
