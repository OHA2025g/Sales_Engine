"""Explicit offer snapshots, mail headers, and the demonstration scope.

Revision ID: 034
Revises: 033

Downgrade is a no-op. It does not drop the new table or the new columns.
Recovery is a restore of the database backup taken before upgrade, followed
by a restart of the API and worker processes that import these models.
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None

_NEW_TABLES = ("demo_scopes",)


def _enable_rls(conn, table: str, using_sql: str) -> None:
    conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    conn.execute(text(f'CREATE POLICY tenant_isolation ON "{table}" USING ({using_sql}) WITH CHECK ({using_sql})'))


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
    _add_column_if_missing(inspector, "operating_plans", sa.Column("context_snapshot", sa.Text(), server_default="", nullable=False))
    _add_column_if_missing(inspector, "email_messages", sa.Column("header_json", sa.Text(), server_default="{}", nullable=False))
    if bind.dialect.name != "postgresql":
        return
    bind.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))
    using = "tenant_id::text = current_setting('app.current_tenant_id', true)"
    names = inspect(bind).get_table_names()
    for table in _NEW_TABLES:
        if table in names:
            _enable_rls(bind, table, using)


def downgrade() -> None:
    return
