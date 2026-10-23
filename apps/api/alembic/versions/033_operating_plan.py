"""Operating plan and immutable creative versions.

Revision ID: 033
Revises: 032

Downgrade is a no-op. It does not drop these tables. Recovery is a restore of
the database backup taken before upgrade, followed by a restart of the API
and worker processes that import these models.
"""

from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None

_NEW_TABLES = ("operating_plans", "creative_versions")


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
    bind.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))
    using = "tenant_id::text = current_setting('app.current_tenant_id', true)"
    names = inspect(bind).get_table_names()
    for table in _NEW_TABLES:
        if table in names:
            _enable_rls(bind, table, using)


def downgrade() -> None:
    return
