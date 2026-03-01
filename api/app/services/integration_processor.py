"""Integration event processors — normalize inbound webhook payloads into True911 entities.

Supported canonical event types:
    - customer_upsert
    - subscription_upsert
    - line_count_update

Non-canonical payloads are marked as 'needs_mapping'.
All operations are idempotent via external_*_map tables + upserts.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.external_customer_map import ExternalCustomerMap
from app.models.external_subscription_map import ExternalSubscriptionMap
from app.models.integration_event import IntegrationEvent
from app.models.job import Job
from app.models.subscription import Subscription

logger = logging.getLogger("true911.integration_processor")

_CANONICAL_TYPES = {"customer_upsert", "subscription_upsert", "line_count_update"}


async def process_integration_event(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Main entry point called by worker dispatch for integration.process.* jobs."""
    payload = job.payload or {}
    event_id = payload.get("integration_event_id")
    if not event_id:
        return {"error": "Missing integration_event_id in job payload"}

    result = await db.execute(select(IntegrationEvent).where(IntegrationEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        return {"error": f"IntegrationEvent {event_id} not found"}

    # Already processed?
    if event.status in ("processed", "processing"):
        return {"skipped": True, "reason": f"Event already {event.status}"}

    event.status = "processing"
    await db.flush()

    try:
        event_payload = event.payload_json or {}
        event_type = event.event_type

        if event_type not in _CANONICAL_TYPES:
            event.status = "needs_mapping"
            event.error = f"Unknown event_type '{event_type}'. Expected one of: {_CANONICAL_TYPES}"
            event.processed_at = datetime.now(timezone.utc)
            await db.flush()
            return {"status": "needs_mapping", "event_type": event_type}

        if event_type == "customer_upsert":
            result_data = await _process_customer_upsert(db, event.org_id, event.source, event_payload)
        elif event_type == "subscription_upsert":
            result_data = await _process_subscription_upsert(db, event.org_id, event.source, event_payload)
        elif event_type == "line_count_update":
            result_data = await _process_line_count_update(db, event.org_id, event.source, event_payload)
        else:
            result_data = {"error": "Unhandled type"}

        event.status = "processed"
        event.processed_at = datetime.now(timezone.utc)
        await db.flush()
        return result_data

    except Exception as exc:
        event.status = "failed"
        event.error = str(exc)
        event.processed_at = datetime.now(timezone.utc)
        await db.flush()
        raise


async def _process_customer_upsert(
    db: AsyncSession, org_id: str, source: str, payload: dict
) -> dict[str, Any]:
    """Upsert a customer from external CRM data.

    Expected payload:
        {org_id, external_account_id, name, email, phone, billing_address, status}
    """
    ext_id = payload.get("external_account_id")
    if not ext_id:
        raise ValueError("Missing external_account_id in customer_upsert payload")

    name = payload.get("name", "Unknown")

    # Check if mapping already exists
    map_result = await db.execute(
        select(ExternalCustomerMap).where(
            ExternalCustomerMap.org_id == org_id,
            ExternalCustomerMap.source == source,
            ExternalCustomerMap.external_account_id == ext_id,
        )
    )
    mapping = map_result.scalar_one_or_none()

    if mapping:
        # Update existing customer
        cust_result = await db.execute(select(Customer).where(Customer.id == mapping.true911_customer_id))
        customer = cust_result.scalar_one_or_none()
        if customer:
            customer.name = name
            customer.billing_email = payload.get("email") or customer.billing_email
            customer.billing_phone = payload.get("phone") or customer.billing_phone
            customer.billing_address = payload.get("billing_address") or customer.billing_address
            customer.status = payload.get("status", customer.status)
            await db.flush()
            return {"action": "updated", "customer_id": customer.id}
    else:
        # Create new customer + mapping
        customer = Customer(
            tenant_id=org_id,
            name=name,
            billing_email=payload.get("email"),
            billing_phone=payload.get("phone"),
            billing_address=payload.get("billing_address"),
            status=payload.get("status", "active"),
        )
        db.add(customer)
        await db.flush()

        db.add(ExternalCustomerMap(
            org_id=org_id,
            source=source,
            external_account_id=ext_id,
            true911_customer_id=customer.id,
        ))
        await db.flush()
        return {"action": "created", "customer_id": customer.id}

    return {"action": "noop"}


async def _process_subscription_upsert(
    db: AsyncSession, org_id: str, source: str, payload: dict
) -> dict[str, Any]:
    """Upsert a subscription from external billing data.

    Expected payload:
        {org_id, external_subscription_id, external_account_id, plan_name, status, mrr, qty_lines, start_date, renewal_date}
    """
    ext_sub_id = payload.get("external_subscription_id")
    ext_acct_id = payload.get("external_account_id")
    if not ext_sub_id:
        raise ValueError("Missing external_subscription_id in subscription_upsert payload")
    if not ext_acct_id:
        raise ValueError("Missing external_account_id in subscription_upsert payload")

    # Resolve customer
    map_result = await db.execute(
        select(ExternalCustomerMap).where(
            ExternalCustomerMap.org_id == org_id,
            ExternalCustomerMap.source == source,
            ExternalCustomerMap.external_account_id == ext_acct_id,
        )
    )
    cust_map = map_result.scalar_one_or_none()
    if not cust_map:
        raise ValueError(f"No customer mapping found for external_account_id={ext_acct_id}. Send customer_upsert first.")

    # Check if subscription mapping exists
    sub_map_result = await db.execute(
        select(ExternalSubscriptionMap).where(
            ExternalSubscriptionMap.org_id == org_id,
            ExternalSubscriptionMap.source == source,
            ExternalSubscriptionMap.external_subscription_id == ext_sub_id,
        )
    )
    sub_map = sub_map_result.scalar_one_or_none()

    def _parse_date(val):
        if not val:
            return None
        if isinstance(val, date):
            return val
        try:
            return date.fromisoformat(val)
        except (ValueError, TypeError):
            return None

    if sub_map:
        # Update existing subscription
        sub_result = await db.execute(select(Subscription).where(Subscription.id == sub_map.true911_subscription_id))
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.plan_name = payload.get("plan_name", sub.plan_name)
            sub.status = payload.get("status", sub.status)
            sub.mrr = payload.get("mrr") if payload.get("mrr") is not None else sub.mrr
            sub.qty_lines = payload.get("qty_lines") if payload.get("qty_lines") is not None else sub.qty_lines
            sub.start_date = _parse_date(payload.get("start_date")) or sub.start_date
            sub.renewal_date = _parse_date(payload.get("renewal_date")) or sub.renewal_date
            await db.flush()
            return {"action": "updated", "subscription_id": sub.id}
    else:
        # Create new subscription + mapping
        sub = Subscription(
            tenant_id=org_id,
            customer_id=cust_map.true911_customer_id,
            plan_name=payload.get("plan_name", "Unknown Plan"),
            status=payload.get("status", "active"),
            mrr=payload.get("mrr"),
            qty_lines=payload.get("qty_lines", 0),
            start_date=_parse_date(payload.get("start_date")),
            renewal_date=_parse_date(payload.get("renewal_date")),
            external_subscription_id=ext_sub_id,
            external_source=source,
        )
        db.add(sub)
        await db.flush()

        db.add(ExternalSubscriptionMap(
            org_id=org_id,
            source=source,
            external_subscription_id=ext_sub_id,
            true911_subscription_id=sub.id,
        ))
        await db.flush()
        return {"action": "created", "subscription_id": sub.id}

    return {"action": "noop"}


async def _process_line_count_update(
    db: AsyncSession, org_id: str, source: str, payload: dict
) -> dict[str, Any]:
    """Update the billed line count on a subscription.

    Expected payload:
        {org_id, external_subscription_id, qty_lines}
    """
    ext_sub_id = payload.get("external_subscription_id")
    if not ext_sub_id:
        raise ValueError("Missing external_subscription_id in line_count_update payload")

    sub_map_result = await db.execute(
        select(ExternalSubscriptionMap).where(
            ExternalSubscriptionMap.org_id == org_id,
            ExternalSubscriptionMap.source == source,
            ExternalSubscriptionMap.external_subscription_id == ext_sub_id,
        )
    )
    sub_map = sub_map_result.scalar_one_or_none()
    if not sub_map:
        raise ValueError(f"No subscription mapping for external_subscription_id={ext_sub_id}")

    sub_result = await db.execute(select(Subscription).where(Subscription.id == sub_map.true911_subscription_id))
    sub = sub_result.scalar_one_or_none()
    if not sub:
        raise ValueError(f"Subscription {sub_map.true911_subscription_id} not found")

    old_qty = sub.qty_lines
    sub.qty_lines = payload.get("qty_lines", sub.qty_lines)
    await db.flush()
    return {"action": "updated", "subscription_id": sub.id, "old_qty": old_qty, "new_qty": sub.qty_lines}
