#!/usr/bin/env python3
"""Read-only diagnostic for a single registration record.

Built after the production silent-attach incident on REG-EE9B668655CC
so operators can answer the question:

  "What did conversion actually produce, and is the attached customer
   legacy data or a freshly-created record?"

Run on the Render shell from the api/ directory:

    cd api
    python -m scripts.inspect_registration REG-EE9B668655CC

Read-only.  Never writes, never deletes, never modifies any row.  If
you decide to clean up a wrong linkage based on this report, the
recommended SQL is documented in the "Manual cleanup" section of the
PR that introduced this script.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta

# Make ``app.*`` importable when run as either
#   python -m scripts.inspect_registration ...
#   python api/scripts/inspect_registration.py ...
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.registration import Registration  # noqa: E402
from app.models.registration_location import RegistrationLocation  # noqa: E402
from app.models.registration_service_unit import RegistrationServiceUnit  # noqa: E402
from app.models.service_unit import ServiceUnit  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.subscription import Subscription  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


# How many days of separation between registration and customer
# creation we treat as "this is probably legacy data".  Anything more
# than a week is suspect — the convert path creates customers in the
# same transaction as the linkage stamp.
LEGACY_THRESHOLD = timedelta(days=7)


def _heading(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print()
    print(bar)
    print(f"  {title}")
    print(bar)


def _row(label: str, value) -> None:
    print(f"  {label:<28} {value if value is not None else '(none)'}")


def _flag(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def _ok(msg: str) -> None:
    print(f"  ✅ {msg}")


async def inspect(registration_id: str) -> int:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Registration).where(Registration.registration_id == registration_id)
        )
        reg = r.scalar_one_or_none()
        if reg is None:
            print(f"Registration {registration_id} not found.")
            return 1

        _heading(f"Registration {reg.registration_id}")
        _row("internal id", reg.id)
        _row("staging tenant_id", reg.tenant_id)
        _row("status", reg.status)
        _row("submitter_email", reg.submitter_email)
        _row("submitter_name", reg.submitter_name)
        _row("customer_name (staging)", reg.customer_name)
        _row("customer_legal_name", reg.customer_legal_name)
        _row("customer_id (stamp)", reg.customer_id)
        _row("target_tenant_id (stamp)", reg.target_tenant_id)
        _row("created_at", reg.created_at)
        _row("submitted_at", reg.submitted_at)
        _row("approved_at", reg.approved_at)
        _row("activated_at", reg.activated_at)
        _row("cancelled_at", reg.cancelled_at)
        if reg.cancel_reason:
            _row("cancel_reason", reg.cancel_reason)

        # ── Customer ──
        legacy_flag = False
        _heading("Attached Customer")
        if not reg.customer_id:
            _row("customer_id", None)
            print("  Not linked to any customer yet.")
        else:
            customer = await db.get(Customer, reg.customer_id)
            if customer is None:
                _flag(
                    f"customer_id={reg.customer_id} is set on the registration but "
                    f"the customer row no longer exists (deleted?).  The "
                    f"materialized linkage is orphaned."
                )
            else:
                _row("id", customer.id)
                _row("name", customer.name)
                _row("tenant_id", customer.tenant_id)
                _row("billing_email", customer.billing_email)
                _row("billing_phone", customer.billing_phone)
                _row("billing_address", customer.billing_address)
                _row("status", customer.status)
                _row("onboarding_status", customer.onboarding_status)
                _row("created_at", customer.created_at)
                _row("updated_at", customer.updated_at)

                # ── Legacy-data heuristics ──
                if customer.created_at and reg.created_at:
                    delta = reg.created_at - customer.created_at
                    if delta > LEGACY_THRESHOLD:
                        _flag(
                            f"customer was created {delta.days} days BEFORE "
                            f"this registration — likely a pre-existing "
                            f"(legacy) record, NOT one created by this convert."
                        )
                        legacy_flag = True
                    elif delta.total_seconds() < -3600:
                        # Customer created well AFTER registration —
                        # normal: convert path made it.
                        pass
                if reg.customer_name and customer.name:
                    norm_reg = " ".join(reg.customer_name.lower().strip().split())
                    norm_cust = " ".join(customer.name.lower().strip().split())
                    if norm_reg != norm_cust:
                        _flag(
                            f"customer name does NOT exactly match the "
                            f"registration's customer_name:\n"
                            f"     registration: '{reg.customer_name}'\n"
                            f"     customer:     '{customer.name}'"
                        )
                        legacy_flag = True
                if customer.tenant_id != reg.target_tenant_id and reg.target_tenant_id:
                    _flag(
                        f"customer.tenant_id ('{customer.tenant_id}') does NOT "
                        f"match registration.target_tenant_id "
                        f"('{reg.target_tenant_id}')."
                    )

        # ── Target tenant ──
        _heading("Target Tenant")
        if not reg.target_tenant_id:
            _row("target_tenant_id", None)
        else:
            r = await db.execute(
                select(Tenant).where(Tenant.tenant_id == reg.target_tenant_id)
            )
            tenant = r.scalar_one_or_none()
            if tenant is None:
                _flag(
                    f"target_tenant_id='{reg.target_tenant_id}' is stamped "
                    f"but no tenant row matches."
                )
            else:
                _row("tenant_id", tenant.tenant_id)
                _row("name", tenant.name)
                _row("created_at", tenant.created_at)

        # ── Locations + materialized Sites ──
        loc_result = await db.execute(
            select(RegistrationLocation)
            .where(RegistrationLocation.registration_id == reg.id)
            .order_by(RegistrationLocation.id.asc())
        )
        locations = list(loc_result.scalars().all())
        _heading(f"Locations ({len(locations)})")
        for loc in locations:
            print(
                f"  - id={loc.id} label='{loc.location_label}' "
                f"address='{loc.street}, {loc.city}, {loc.state} {loc.zip}'"
            )
            if loc.materialized_site_id is None:
                print("    materialized_site_id: (none)")
            else:
                site = await db.get(Site, loc.materialized_site_id)
                if site is None:
                    _flag(
                        f"    materialized_site_id={loc.materialized_site_id} "
                        f"is set but no site row matches."
                    )
                else:
                    print(
                        f"    -> Site id={site.id} site_id='{site.site_id}' "
                        f"tenant_id='{site.tenant_id}' "
                        f"customer_id={site.customer_id} "
                        f"customer_name='{site.customer_name}'"
                    )

        # ── Service units + materialized ServiceUnits ──
        unit_result = await db.execute(
            select(RegistrationServiceUnit)
            .where(RegistrationServiceUnit.registration_id == reg.id)
            .order_by(RegistrationServiceUnit.id.asc())
        )
        reg_units = list(unit_result.scalars().all())
        _heading(f"Service Units ({len(reg_units)})")
        for ru in reg_units:
            print(
                f"  - id={ru.id} label='{ru.unit_label}' type='{ru.unit_type}' "
                f"location_id={ru.registration_location_id} "
                f"phone='{ru.phone_number_existing}'"
            )
            if ru.materialized_service_unit_id is None:
                print("    materialized_service_unit_id: (none)")
            else:
                u = await db.get(ServiceUnit, ru.materialized_service_unit_id)
                if u is None:
                    _flag(
                        f"    materialized_service_unit_id="
                        f"{ru.materialized_service_unit_id} is set but no "
                        f"service_unit row matches."
                    )
                else:
                    print(
                        f"    -> ServiceUnit id={u.id} unit_id='{u.unit_id}' "
                        f"site_id='{u.site_id}' tenant_id='{u.tenant_id}'"
                    )

        # ── Subscription ──
        _heading("Subscription")
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.external_subscription_id == f"reg:{reg.registration_id}",
                Subscription.external_source == "registration",
            )
        )
        sub = sub_result.scalar_one_or_none()
        if sub is None:
            print("  (none)")
        else:
            _row("id", sub.id)
            _row("plan_name", sub.plan_name)
            _row("status", sub.status)
            _row("customer_id", sub.customer_id)
            _row("tenant_id", sub.tenant_id)
            _row("qty_lines", sub.qty_lines)
            _row("created_at", sub.created_at)

        # ── Summary ──
        _heading("Summary")
        if legacy_flag:
            _flag(
                "The attached customer appears to be LEGACY data, not a "
                "record this conversion created.  Manual cleanup is "
                "probably needed — see the PR description for the SQL."
            )
        else:
            _ok("No legacy-data indicators detected for the attached customer.")

        return 0


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage:\n"
            "    python -m scripts.inspect_registration REG-XXXXXXXXXXXX\n"
            "\n"
            "Reads:\n"
            "    registrations / registration_locations / registration_service_units\n"
            "    customers / tenants / sites / service_units / subscriptions\n"
            "\n"
            "Writes:\n"
            "    nothing — this script is strictly read-only."
        )
        return 2
    return asyncio.run(inspect(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
