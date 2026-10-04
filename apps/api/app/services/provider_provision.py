from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.provider_accounts import upsert_token_account
from app.services.provider_resolve import resolve_channel


def _present(values: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


def _distinct_secret(candidate: str, primary: str) -> str:
    if candidate and candidate != primary:
        return candidate
    return ""


def provision_env_credentials(db: Session, *, tenant_id: UUID, actor_id: UUID) -> list[str]:
    """Copy deployment secrets into tenant ProviderAccount rows so resolve_channel reports tenant credential."""
    settings = get_settings()
    provisioned: list[str] = []
    specs: list[tuple[str, str, dict]] = []
    linkedin_token = settings.linkedin_access_token or settings.linkedin_post_access_token
    if linkedin_token and (settings.linkedin_ads_configured or settings.linkedin_posting_configured):
        specs.append(
            (
                "linkedin",
                linkedin_token,
                _present(
                    {
                        "account_id": settings.linkedin_ad_account_id,
                        "organization_id": settings.linkedin_organization_id,
                        "ads_mode": settings.linkedin_ads_mode,
                        "posting_mode": settings.linkedin_posting_mode,
                        "post_access_token": _distinct_secret(settings.linkedin_post_access_token, linkedin_token),
                    }
                ),
            )
        )
    meta_token = settings.meta_ads_token or settings.meta_page_access_token
    if meta_token and (settings.meta_ads_configured or settings.meta_page_posting_configured):
        specs.append(
            (
                "meta",
                meta_token,
                _present(
                    {
                        "account_id": settings.resolved_meta_ad_account_id,
                        "ads_mode": settings.meta_ads_mode,
                        "page_id": settings.meta_page_id,
                        "instagram_business_account_id": settings.instagram_business_account_id,
                        "posting_mode": settings.meta_posting_mode,
                        "page_access_token": _distinct_secret(settings.meta_page_access_token, meta_token),
                    }
                ),
            )
        )
    if settings.twilio_configured:
        specs.append(
            (
                "twilio",
                settings.twilio_auth_token,
                {
                    "account_sid": settings.twilio_account_sid,
                    "from_number": settings.twilio_from_number,
                    "twiml_url": settings.twilio_twiml_url,
                },
            )
        )
    if settings.dograh_configured:
        specs.append(
            (
                "dograh",
                settings.dograh_api_key,
                {"agent_uuid": settings.dograh_agent_uuid, "api_base": settings.dograh_api_base},
            )
        )
    if settings.vapi_configured:
        specs.append(
            (
                "vapi",
                settings.vapi_api_key,
                {"assistant_id": settings.vapi_assistant_id, "phone_number_id": settings.vapi_phone_number_id},
            )
        )
    if settings.exotel_configured:
        specs.append(
            (
                "exotel",
                settings.exotel_api_token,
                {
                    "sid": settings.exotel_sid,
                    "api_key": settings.exotel_api_key,
                    "caller_id": settings.exotel_caller_id,
                    "subdomain": settings.exotel_subdomain,
                },
            )
        )
    if settings.apify_configured:
        specs.append(
            (
                "apify",
                settings.resolved_apify_token,
                {"actor_id": settings.apify_actor_id, "process_token": settings.apify_linkedin_process_token},
            )
        )
    if settings.gemini_configured:
        specs.append(("gemini", settings.gemini_api_key, {"default_model": settings.gemini_default_model}))
    if settings.recall_configured:
        specs.append(("recall", settings.recall_api_key, {}))
    if settings.enrichment_configured:
        specs.append(("enrichment", settings.enrichment_api_key, {"base_url": settings.enrichment_api_base}))
    for provider, token, extra in specs:
        if not token:
            continue
        upsert_token_account(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            provider=provider,
            access_token=token,
            extra=extra,
        )
        provisioned.append(provider)
    db.flush()
    return provisioned


def channel_modes(db: Session, tenant_id: UUID) -> dict[str, dict[str, str | bool]]:
    keys = ("email", "calendar", "discovery", "linkedin", "meta", "twilio", "vapi", "dograh", "exotel", "gemini", "recall", "enrichment")
    rows: dict[str, dict[str, str | bool]] = {}
    for key in keys:
        resolved = resolve_channel(db, tenant_id, key)
        rows[key] = {
            "mode": resolved.mode,
            "reason": resolved.reason,
            "uses_deployment_default": resolved.uses_deployment_default,
            "tenant_credential": bool(resolved.account_id),
        }
    return rows
