"""Store uploaded social images and let a public link read one image.

Revision ID: 026
Revises: 025
"""

from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return
    if "social_images" not in inspect(bind).get_table_names():
        return
    using = (
        "tenant_id::text = current_setting('app.current_tenant_id', true) "
        "OR (current_setting('app.form_token_hash', true) <> '' "
        "AND token_hash = current_setting('app.form_token_hash', true))"
    )
    conn = bind
    conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))
    conn.execute(text('ALTER TABLE "social_images" ENABLE ROW LEVEL SECURITY'))
    conn.execute(text('ALTER TABLE "social_images" FORCE ROW LEVEL SECURITY'))
    conn.execute(text('DROP POLICY IF EXISTS tenant_isolation ON "social_images"'))
    conn.execute(text(f'CREATE POLICY tenant_isolation ON "social_images" USING ({using}) WITH CHECK ({using})'))


def downgrade() -> None:
    return
