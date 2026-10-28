import json

from app.models.ai import AIApproval
from app.schemas.ai import ApprovalOut


def approval_out(row: AIApproval) -> ApprovalOut:
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    who = str(payload.get("who") or payload.get("lead_id") or payload.get("customer_id") or payload.get("campaign_id") or row.entity_id or "")
    message = str(payload.get("body") or payload.get("template") or "")
    missing = payload.get("missing_information")
    missing_text = ", ".join(str(item) for item in missing) if isinstance(missing, list) else str(missing or "")
    action = row.action_type
    category = "SALES"
    if action.startswith("customer.") or "success" in action:
        category = "CUSTOMER SUCCESS"
    elif action.startswith("renewal."):
        category = "RENEWAL"
    elif action.startswith("expansion.") or action.startswith("upsell") or action.startswith("cross_sell"):
        category = "EXPANSION"
    elif action.startswith("advocacy."):
        category = "ADVOCACY"
    elif action.startswith("mapping."):
        category = "INTEGRATIONS"
    elif action.startswith("social."):
        category = "MARKETING"
    return ApprovalOut(
        id=row.id,
        action_level=row.action_level,
        action_type=row.action_type,
        title=row.title,
        payload_json=row.payload_json,
        status=row.status,
        decision_note=row.decision_note,
        run_id=row.run_id,
        entity_type=row.entity_type or str(payload.get("entity_type") or ""),
        entity_id=row.entity_id or str(payload.get("lead_id") or payload.get("campaign_id") or ""),
        who=who,
        why=str(payload.get("why") or "Autopilot prepared a governed action."),
        evidence=str(payload.get("evidence") or ""),
        risk=str(payload.get("risk") or "External or commercial action requires a human gate."),
        expected_outcome=str(payload.get("expected_outcome") or ""),
        message=message,
        subject=str(payload.get("subject") or ""),
        product_name=str(payload.get("product_name") or ""),
        generation=str(payload.get("generation") or ""),
        context_version=str(payload.get("context_version") or ""),
        personalisation=_personalisation(payload),
        missing_information=missing_text,
        eligibility=str(payload.get("eligibility") or ""),
        next_action=str(payload.get("next_action") or ""),
        commercial_impact=str(payload.get("commercial_impact") or ""),
        budget_impact=str(payload.get("budget") or payload.get("budget_impact") or ""),
        category=category,
    )


def _personalisation(payload: dict) -> str:
    raw = payload.get("personalisation")
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, dict):
        return ""
    lines: list[str] = []
    labels = (
        ("Customer-supplied", "customer_supplied"),
        ("Sourced observations", "sourced_observations"),
        ("Inferences", "inferences"),
        ("Unsupported", "unsupported"),
    )
    for label, key in labels:
        items = raw.get(key) or []
        if isinstance(items, list) and items:
            lines.append(f"{label}: " + "; ".join(str(item) for item in items))
    refs = payload.get("evidence_references") or []
    if isinstance(refs, list) and refs:
        lines.append("References: " + "; ".join(str(item) for item in refs))
    return "\n".join(lines)
