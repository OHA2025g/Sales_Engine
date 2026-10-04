"""Recurring revenue, period forecast, and cohort retention.

Opportunity amount is a booking candidate. Annual recurring revenue comes only
from recurring contract lines.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import Customer, Opportunity
from app.models.execution import CampaignPlan, RevenueCohortSnapshot
from app.models.lifecycle import Product, QuoteLine
from app.models.post_sale import Contract, ContractLine


def _money(value: Decimal | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def line_kind(db: Session, line: QuoteLine | ContractLine) -> str:
    product_id = getattr(line, "product_id", None)
    if product_id is None:
        return "one_time"
    product = db.get(Product, product_id)
    if product is None:
        return "one_time"
    return "recurring" if (product.kind or "subscription") == "subscription" else "one_time"


def annualized(kind: str, amount: Decimal, term_months: int | None) -> Decimal:
    if kind != "recurring":
        return Decimal("0.00")
    months = term_months or 12
    if months <= 0:
        return _money(amount)
    return _money(amount * Decimal(12) / Decimal(months))


def rollup_customer_arr(db: Session, *, tenant_id: UUID, customer: Customer) -> Decimal:
    lines = db.scalars(
        select(ContractLine)
        .join(Contract, Contract.id == ContractLine.contract_id)
        .where(
            Contract.tenant_id == tenant_id,
            Contract.customer_id == customer.id,
            Contract.deleted_at.is_(None),
            ContractLine.deleted_at.is_(None),
            Contract.status.notin_(["cancelled", "churned"]),
        )
    ).all()
    total = Decimal("0.00")
    for line in lines:
        kind = line.billing_kind or "recurring"
        amount = line.annualized_amount if line.annualized_amount is not None else annualized(kind, _money(line.line_total), None)
        if kind == "recurring":
            total += _money(amount)
    customer.arr = total
    return total


def stamp_contract_line(db: Session, line: ContractLine, *, opportunity_id: UUID | None = None) -> None:
    kind = line.billing_kind or line_kind(db, line)
    line.billing_kind = kind
    line.annualized_amount = annualized(kind, _money(line.line_total), None)
    if opportunity_id is not None:
        line.source_opportunity_id = opportunity_id


def remember_opening_cohort(db: Session, *, tenant_id: UUID, actor_id: UUID, customer: Customer) -> None:
    period = date.today().strftime("%Y-%m")
    existing = db.scalar(
        select(RevenueCohortSnapshot).where(
            RevenueCohortSnapshot.tenant_id == tenant_id,
            RevenueCohortSnapshot.period == period,
            RevenueCohortSnapshot.deleted_at.is_(None),
        )
    )
    opening = rollup_customer_arr(db, tenant_id=tenant_id, customer=customer)
    if existing is None:
        db.add(
            RevenueCohortSnapshot(
                tenant_id=tenant_id,
                created_by=actor_id,
                period=period,
                opening_arr=opening,
            )
        )
        return
    if existing.opening_arr == 0 and opening > 0:
        existing.opening_arr = opening


def record_cohort_movement(
    db: Session,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    kind: str,
    amount: Decimal,
) -> None:
    period = date.today().strftime("%Y-%m")
    row = db.scalar(
        select(RevenueCohortSnapshot).where(
            RevenueCohortSnapshot.tenant_id == tenant_id,
            RevenueCohortSnapshot.period == period,
            RevenueCohortSnapshot.deleted_at.is_(None),
        )
    )
    if row is None:
        row = RevenueCohortSnapshot(tenant_id=tenant_id, created_by=actor_id, period=period, opening_arr=Decimal("0"))
        db.add(row)
        db.flush()
    value = _money(amount)
    if kind == "churn":
        row.churn_arr = _money(row.churn_arr) + value
    elif kind == "contraction":
        row.contraction_arr = _money(row.contraction_arr) + value
    elif kind == "expansion":
        row.expansion_arr = _money(row.expansion_arr) + value


def retention_metrics(db: Session, tenant_id: UUID) -> dict:
    points = db.scalars(
        select(RevenueCohortSnapshot)
        .where(RevenueCohortSnapshot.tenant_id == tenant_id, RevenueCohortSnapshot.deleted_at.is_(None))
        .order_by(RevenueCohortSnapshot.period.asc())
    ).all()
    if len(points) < 1 or all(_money(row.opening_arr) == 0 for row in points):
        return {
            "grr": None,
            "nrr": None,
            "status": "unavailable",
            "reason": "Retention needs an opening recurring cohort. No measured cohort is stored yet.",
        }
    opening = _money(points[0].opening_arr)
    if opening <= 0:
        return {"grr": None, "nrr": None, "status": "unavailable", "reason": "Opening recurring revenue is zero."}
    churn = sum((_money(row.churn_arr) for row in points), Decimal("0"))
    contraction = sum((_money(row.contraction_arr) for row in points), Decimal("0"))
    expansion = sum((_money(row.expansion_arr) for row in points), Decimal("0"))
    if churn == 0 and contraction == 0 and expansion == 0 and len(points) < 2:
        return {
            "grr": None,
            "nrr": None,
            "status": "unavailable",
            "reason": "An opening cohort exists, but no later churn, contraction, or expansion has been recorded.",
            "opening_arr": str(opening),
        }
    grr = (opening - churn - contraction) / opening
    nrr = (opening - churn - contraction + expansion) / opening
    return {
        "grr": float(grr.quantize(Decimal("0.0001"))),
        "nrr": float(nrr.quantize(Decimal("0.0001"))),
        "status": "measured",
        "opening_arr": str(opening),
        "churn_arr": str(churn),
        "contraction_arr": str(contraction),
        "expansion_arr": str(expansion),
    }


def opportunities_for_period(rows: list[Opportunity], period: str) -> tuple[list[Opportunity], list[Opportunity]]:
    in_period: list[Opportunity] = []
    unscheduled: list[Opportunity] = []
    for row in rows:
        if row.expected_close is None:
            unscheduled.append(row)
            continue
        if row.expected_close.strftime("%Y-%m") == period:
            in_period.append(row)
    return in_period, unscheduled


def approved_ad_budget(db: Session, *, tenant_id: UUID, channel: str, product_id: UUID | None) -> CampaignPlan | None:
    rows = db.scalars(
        select(CampaignPlan).where(
            CampaignPlan.tenant_id == tenant_id,
            CampaignPlan.deleted_at.is_(None),
            CampaignPlan.status == "approved",
            CampaignPlan.channel == channel,
            CampaignPlan.budget > 0,
        )
    ).all()
    for row in rows:
        if product_id is not None and row.product_id not in {None, product_id}:
            continue
        if _money(row.spent) >= _money(row.budget):
            continue
        return row
    return None
