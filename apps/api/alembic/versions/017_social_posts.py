"""Organic social posts for LinkedIn and Meta.

Revision ID: 017
Revises: 016
"""

from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def _enable_rls(conn, table: str, using_sql: str) -> None:
    conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    conn.execute(text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    conn.execute(text(f'CREATE POLICY tenant_isolation ON "{table}" USING ({using_sql}) WITH CHECK ({using_sql})'))


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return
    conn = bind
    conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))
    if "social_posts" in inspect(bind).get_table_names():
        _enable_rls(conn, "social_posts", "tenant_id::text = current_setting('app.current_tenant_id', true)")


def downgrade() -> None:
    return
