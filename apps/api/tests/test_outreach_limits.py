from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session
from app.models.crm import Lead
from app.models.identity import User
from app.models.integrations import EmailMessage
from app.models.lifecycle import Conversation
from app.services.autopilot_settings import get_or_create_settings
from app.services.outreach_limits import outreach_limit_reason


def test_interest_skips_the_minimum_gap(client: TestClient) -> None:
    _ = client
    db = get_session()
    user = db.scalar(select(User).where(User.email == "admin@agrayian.demo"))
    assert user is not None
    settings = get_or_create_settings(db, tenant_id=user.tenant_id, actor_id=user.id)
    settings.minimum_hours_between_outreach = 24
    settings.max_emails_per_day = 0
    settings.max_emails_per_contact_per_day = 0
    interested = Lead(
        tenant_id=user.tenant_id,
        created_by=user.id,
        first_name="Interested",
        last_name="Buyer",
        email="interested.buyer@example.com",
        consent_email=True,
    )
    cold = Lead(
        tenant_id=user.tenant_id,
        created_by=user.id,
        first_name="Cold",
        last_name="Buyer",
        email="cold.buyer@example.com",
        consent_email=True,
    )
    db.add_all([interested, cold])
    db.flush()
    sent_at = datetime.now(UTC) - timedelta(hours=1)
    for lead, classification, direction in (
        (interested, "", "outbound"),
        (interested, "POSITIVE_INTEREST", "inbound"),
        (cold, "", "outbound"),
    ):
        conversation = Conversation(tenant_id=user.tenant_id, created_by=user.id, lead_id=lead.id, channel="email")
        db.add(conversation)
        db.flush()
        db.add(
            EmailMessage(
                tenant_id=user.tenant_id,
                created_by=user.id,
                conversation_id=conversation.id,
                lead_id=lead.id,
                direction=direction,
                provider="gmail",
                provider_message_id=f"{lead.id}-{direction}",
                status="SENT",
                sent_at=sent_at,
                received_at=sent_at,
                classification=classification,
            )
        )
    db.flush()
    try:
        assert outreach_limit_reason(db, settings, interested.id) is None
        assert outreach_limit_reason(db, settings, cold.id) == "Minimum hours between outreach not elapsed"
    finally:
        db.rollback()
