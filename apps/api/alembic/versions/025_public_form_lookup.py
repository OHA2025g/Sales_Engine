"""Let a visitor open one public form by its token.

Revision ID: 025
Revises: 024
"""

from sqlalchemy import inspect, text

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if "public_form_keys" not in inspect(bind).get_table_names():
        return
    using = (
        "tenant_id::text = current_setting('app.current_tenant_id', true) "
        "OR (current_setting('app.form_token_hash', true) <> '' "
        "AND token_hash = current_setting('app.form_token_hash', true))"
    )
    bind.execute(text('ALTER TABLE "public_form_keys" ENABLE ROW LEVEL SECURITY'))
    bind.execute(text('ALTER TABLE "public_form_keys" FORCE ROW LEVEL SECURITY'))
    bind.execute(text('DROP POLICY IF EXISTS tenant_isolation ON "public_form_keys"'))
    bind.execute(text(f'CREATE POLICY tenant_isolation ON "public_form_keys" USING ({using}) WITH CHECK ({using})'))


def downgrade() -> None:
    return
