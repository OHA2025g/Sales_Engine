"""Revenue workflow execution contracts.

Revision ID: 020
Revises: 019
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op
from app.db.base import Base
from app.models import *  # noqa: F403

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "event_delivery_attempts",
    "action_requests",
    "authorization_grants",
    "revenue_objectives",
    "campaign_plans",
    "stage_evidence",
    "eligibility_evidence",
    "sla_clocks",
    "journey_links",
    "account_scan_cursors",
    "revenue_cohort_snapshots",
    "user_invitations",
    "operational_evidence",
)


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
    _add_column_if_missing(inspector, "domain_events", sa.Column("delivery_status", sa.String(20), nullable=False, server_default="pending"))
    _add_column_if_missing(inspector, "domain_events", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "domain_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(inspector, "domain_events", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(inspector, "domain_events", sa.Column("lease_token", sa.String(64), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "domain_events", sa.Column("last_error", sa.Text(), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "domain_events", sa.Column("consumer", sa.String(40), nullable=False, server_default="orchestrator"))
    _add_column_if_missing(inspector, "autopilot_settings", sa.Column("social_channel_paused", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing(inspector, "entity_automation_states", sa.Column("business_state", sa.String(40), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "entity_automation_states", sa.Column("execution_status", sa.String(20), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "entity_automation_states", sa.Column("evaluation_key", sa.String(64), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "entity_automation_states", sa.Column("resume_step", sa.String(40), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "sequences", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    _add_column_if_missing(inspector, "sequences", sa.Column("icp_id", sa.Uuid(), nullable=True))
    _add_column_if_missing(inspector, "sequences", sa.Column("campaign_id", sa.Uuid(), nullable=True))
    _add_column_if_missing(inspector, "sequences", sa.Column("offer_key", sa.String(80), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "sequences", sa.Column("routing_priority", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing(inspector, "quotes", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    _add_column_if_missing(inspector, "quotes", sa.Column("terms", sa.Text(), nullable=False, server_default=""))
    _add_column_if_missing(inspector, "quotes", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(inspector, "quotes", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(inspector, "playbooks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    _add_column_if_missing(inspector, "playbooks", sa.Column("conditions_json", sa.Text(), nullable=False, server_default="{}"))
    _add_column_if_missing(inspector, "playbooks", sa.Column("status", sa.String(20), nullable=False, server_default="active"))
    _add_column_if_missing(inspector, "contract_lines", sa.Column("billing_kind", sa.String(20), nullable=False, server_default="recurring"))
    _add_column_if_missing(inspector, "contract_lines", sa.Column("annualized_amount", sa.Numeric(18, 2), nullable=True))
    _add_column_if_missing(inspector, "contract_lines", sa.Column("source_opportunity_id", sa.Uuid(), nullable=True))
    _add_column_if_missing(inspector, "scheduler_heartbeats", sa.Column("leader_token", sa.String(64), nullable=False, server_default=""))
    if bind.dialect.name != "postgresql":
        return
    conn = bind
    conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agrayian_app"))
    using = "tenant_id::text = current_setting('app.current_tenant_id', true)"
    names = inspect(bind).get_table_names()
    for table in NEW_TABLES:
        if table in names:
            _enable_rls(conn, table, using)


def downgrade() -> None:
    return
