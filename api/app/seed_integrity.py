"""Idempotent onboarding of Integrity Property Management — Belle Terre at Sunrise.

This materialises a single, known real-customer deployment into production
tables.  It is deliberately *not* an Alembic migration: customer/site/device
data does not belong in a migration that auto-runs on every environment.
Instead it follows the standalone-script pattern of ``scripts/repair_device_tenant.py``
— ``DRY_RUN`` defaults to **true**, so nothing is written unless you pass
``DRY_RUN=false`` explicitly.

What it creates (insert-if-absent, never destructive):

    Tenant     integrity-pm  "Integrity Property Management"
      Customer  "Integrity Property Management"  (Zoho account 337391000069074135)
      Sites
        IPM-BELLE-TERRE      Belle Terre at Sunrise   (full e911 address — active)
        IPM-POMPANO          The Pointe of Pompano Beach Condo Association
                             (pending + TEST — Zoho-flagged test location, inert)
        IPM-TIFFANY-EAST     Tiffany Gardens East         (pending — no e911 yet)
        IPM-TIFFANY-NORTH    Tiffany Gardens North        (pending — no e911 yet)
      Service units (under Belle Terre)
        Elevator 1 / 2 / 3   (unit_type=elevator_phone)
      Devices (under Belle Terre)
        3 × FlyingVoice LM150 VoLTE  (serial / IMEI / ICCID / MSISDN, carrier=tmobile)
      SIMs
        3 × T-Mobile VoLTE SIMs  (+ DeviceSim slot-1 links)
      User
        1 × Admin invite (env INTEGRITY_ADMIN_EMAIL)

Run
---
    # dry run — prints the full plan, writes nothing (default)
    python -m app.seed_integrity

    # apply for real
    DRY_RUN=false python -m app.seed_integrity

    # apply + create the admin invite with a specific email
    DRY_RUN=false INTEGRITY_ADMIN_EMAIL=cindy@ipmflorida.com python -m app.seed_integrity

Safety / idempotency
--------------------
* Every entity is matched on its natural key (tenant slug, site_id, unit_id,
  device serial, SIM iccid, user email) and inserted **only when absent**.
* Existing rows are never overwritten.  Re-running is a no-op apart from
  back-filling a missing ``customer_id`` FK / ``zoho_account_id`` that we can
  set authoritatively.
* The three placeholder properties are created with ``status=pending`` and
  **no e911 address** — life-safety data is never fabricated.  Supply verified
  addresses later (portal or a follow-up run) to activate them.

NOTE on field coverage (documented gaps, no schema change made here):
* There is no native ``volte_enabled`` column.  We record it in ``Sim.meta``
  and in the device notes.
* There is no per-device Zoho column.  The Zoho link lives on the Customer
  (``zoho_account_id``); the device notes carry the account id for traceability.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys

# Make ``app.*`` importable when run as ``python -m app.seed_integrity`` from
# the ``api`` directory, and also when invoked from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Identity / constants ─────────────────────────────────────────────
TENANT_ID = "integrity-pm"
TENANT_NAME = "Integrity Property Management"

# Confirmed read-only from Zoho CRM (Accounts) on 2026-06-01.
ZOHO_ACCOUNT_ID = "337391000069074135"
CUSTOMER_NUMBER = "15137"          # Zoho Customer_Account_Number
BILLING_EMAIL = "Cindy@ipmflorida.com"
BILLING_PHONE = "(954) 346-0677"

LM150_HARDWARE_MODEL_ID = "flyingvoice-lm150"  # seeded by migration 046
LM150_MODEL = "LM150"
LM150_DEVICE_TYPE = "VoLTE ATA"
LM150_MANUFACTURER = "FlyingVoice"

CARRIER = "tmobile"

BELLE_TERRE_SITE_ID = "IPM-BELLE-TERRE"

ASSIGNED_BY = "onboard:integrity-belle-terre"

# ── Sites ────────────────────────────────────────────────────────────
# Belle Terre carries the only verified e911 address.  The other three are
# created as pending placeholders (no e911) so the parent/child hierarchy is
# visible without fabricating life-safety data.
SITES: list[dict] = [
    {
        "site_id": BELLE_TERRE_SITE_ID,
        "site_name": "Belle Terre at Sunrise",
        "status": "active",
        "onboarding_status": "active",
        "e911_street": "7800 W Oakland Park Blvd",
        "e911_city": "Sunrise",
        "e911_state": "FL",
        "e911_zip": "33351",
        "e911_status": "provided",
        "e911_confirmation_required": False,
        "carrier": CARRIER,
        "building_type": "residential",
        "address_source": "customer_intake",
    },
    {
        # Name matches Zoho exactly. Zoho flags this as a test location
        # ("House Account - Test location"), so it is created inert: pending,
        # not active, and explicitly marked TEST so it never reads as a live
        # life-safety deployment until manually activated.
        "site_id": "IPM-POMPANO",
        "site_name": "The Pointe of Pompano Beach Condo Association",
        "status": "pending",
        "onboarding_status": "test",
        "e911_status": "missing",
        "e911_confirmation_required": True,
        "notes": (
            "TEST LOCATION — Zoho-flagged 'House Account - Test location' "
            "(child of Integrity Property Management). NOT a live deployment. "
            "Do not activate."
        ),
        "address_notes": (
            "Awaiting verified e911 address. Zoho account: 'The Pointe of "
            "Pompano Beach Condo Association' (test location, child of "
            "Integrity). DO NOT route emergency calls until a verified "
            "address is supplied."
        ),
    },
    {
        "site_id": "IPM-TIFFANY-EAST",
        "site_name": "Tiffany Gardens East",
        "status": "pending",
        "onboarding_status": "pending",
        "e911_status": "missing",
        "e911_confirmation_required": True,
        "address_notes": (
            "Awaiting verified e911 address. Zoho account: 'Tiffany Gardens "
            "- East' exists but is not yet linked to the Integrity parent. "
            "DO NOT route emergency calls until a verified address is supplied."
        ),
    },
    {
        "site_id": "IPM-TIFFANY-NORTH",
        "site_name": "Tiffany Gardens North",
        "status": "pending",
        "onboarding_status": "pending",
        "e911_status": "missing",
        "e911_confirmation_required": True,
        "address_notes": (
            "Awaiting verified e911 address. No matching Zoho account found "
            "for 'Tiffany Gardens North'. DO NOT route emergency calls until "
            "a verified address is supplied."
        ),
    },
]

# ── Devices (Belle Terre elevators) ──────────────────────────────────
DEVICES: list[dict] = [
    {"elevator": 1, "serial": "VOLA00325600226", "imei": "355893730016754",
     "iccid": "8901240204219433645", "msisdn": "7542697860"},
    {"elevator": 2, "serial": "VOLA00325600227", "imei": "355893730016762",
     "iccid": "8901240204219433652", "msisdn": "7542528836"},
    {"elevator": 3, "serial": "VOLA00325600230", "imei": "355893730016796",
     "iccid": "8901240204219166351", "msisdn": "7542653349"},
]

# Expose the serials so the verify script / tests share one source of truth.
EXPECTED_SERIALS = [d["serial"] for d in DEVICES]
EXPECTED_ICCIDS = [d["iccid"] for d in DEVICES]


# ── Pure builders (no DB / no I/O — unit-testable) ───────────────────
def device_id_for(serial: str) -> str:
    """Match the id scheme the Vola sync would generate (``VOLA-<sn>``) so a
    later carrier/Vola sync reconciles to this row instead of duplicating it."""
    return f"VOLA-{serial}"


def unit_id_for(elevator: int) -> str:
    return f"{BELLE_TERRE_SITE_ID}-EL{elevator}"


def build_tenant_kwargs() -> dict:
    return {
        "tenant_id": TENANT_ID,
        "name": TENANT_NAME,
        "org_type": "customer",
        "display_name": TENANT_NAME,
        "contact_email": BILLING_EMAIL,
        "contact_phone": BILLING_PHONE,
        "zoho_account_id": ZOHO_ACCOUNT_ID,
        "is_active": True,
    }


def build_customer_kwargs() -> dict:
    return {
        "tenant_id": TENANT_ID,
        "name": TENANT_NAME,
        "customer_number": CUSTOMER_NUMBER,
        "billing_email": BILLING_EMAIL,
        "billing_phone": BILLING_PHONE,
        "status": "active",
        "zoho_account_id": ZOHO_ACCOUNT_ID,
        "zoho_sync_status": "synced",
        "onboarding_status": "in_progress",
    }


def build_site_kwargs(spec: dict) -> dict:
    """Translate a SITES spec entry into Site(**kwargs)."""
    kw = {
        "site_id": spec["site_id"],
        "tenant_id": TENANT_ID,
        "site_name": spec["site_name"],
        "customer_name": TENANT_NAME,
        "status": spec["status"],
        "onboarding_status": spec["onboarding_status"],
    }
    for opt in (
        "e911_street", "e911_city", "e911_state", "e911_zip", "e911_status",
        "e911_confirmation_required", "carrier", "building_type",
        "address_source", "address_notes", "notes",
    ):
        if opt in spec:
            kw[opt] = spec[opt]
    return kw


def build_service_unit_kwargs(d: dict) -> dict:
    n = d["elevator"]
    return {
        "tenant_id": TENANT_ID,
        "site_id": BELLE_TERRE_SITE_ID,
        "unit_id": unit_id_for(n),
        "unit_name": f"Elevator {n}",
        "unit_type": "elevator_phone",
        "location_description": f"Elevator {n}",
        "voice_supported": True,
        "device_id": device_id_for(d["serial"]),
        "status": "active",
        "meta": {"elevator": n, "source": ASSIGNED_BY},
    }


def build_device_kwargs(d: dict, *, vola_org_id: str | None = None,
                        status: str = "active") -> dict:
    n = d["elevator"]
    notes = (
        f"Belle Terre at Sunrise — Elevator {n}. "
        "VoLTE enabled. Vola Cloud managed. T-Mobile VoLTE SIM. "
        f"Zoho account {ZOHO_ACCOUNT_ID}."
    )
    return {
        "device_id": device_id_for(d["serial"]),
        "tenant_id": TENANT_ID,
        "site_id": BELLE_TERRE_SITE_ID,
        "status": status,
        "device_type": LM150_DEVICE_TYPE,
        "model": LM150_MODEL,
        "manufacturer": LM150_MANUFACTURER,
        "hardware_model_id": LM150_HARDWARE_MODEL_ID,
        "serial_number": d["serial"],
        "imei": d["imei"],
        "iccid": d["iccid"],
        "msisdn": d["msisdn"],
        "carrier": CARRIER,
        "identifier_type": "cellular",
        "vola_org_id": vola_org_id or None,
        "telemetry_source": "tmobile_callback",
        "notes": notes,
    }


def build_sim_kwargs(d: dict) -> dict:
    return {
        "tenant_id": TENANT_ID,
        "iccid": d["iccid"],
        "msisdn": d["msisdn"],
        "imei": d["imei"],
        "carrier": CARRIER,
        "status": "active",
        "site_id": BELLE_TERRE_SITE_ID,
        "device_id": device_id_for(d["serial"]),
        "data_source": "manual",
        "reconciliation_status": "partial",
        "meta": {
            "volte_enabled": True,
            "carrier_display": "T-Mobile",
            "elevator": d["elevator"],
            "source": ASSIGNED_BY,
        },
    }


def build_admin_user_kwargs(email: str, token: str, password_hash: str,
                            expires_at: _dt.datetime) -> dict:
    return {
        "email": email,
        "name": "Integrity Property Management Admin",
        "password_hash": password_hash,
        "role": "Admin",
        "tenant_id": TENANT_ID,
        "is_active": False,
        "invite_token": token,
        "invite_expires_at": expires_at,
    }


# ── Apply layer (DB I/O — heavy imports kept local) ──────────────────
async def _get_scalar(db, stmt):
    return (await db.execute(stmt)).scalar_one_or_none()


async def apply(dry_run: bool = True, admin_email: str | None = None) -> dict:
    """Idempotently create the Integrity / Belle Terre records.

    Returns a summary dict of created/existing counts.  Writes nothing when
    ``dry_run`` is True.
    """
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.config import settings
    from app.models.tenant import Tenant
    from app.models.customer import Customer
    from app.models.site import Site
    from app.models.service_unit import ServiceUnit
    from app.models.device import Device
    from app.models.sim import Sim
    from app.models.device_sim import DeviceSim
    from app.models.user import User
    from app.services.auth import generate_invite_token, hash_password

    import secrets

    summary: dict[str, list[str]] = {
        "created": [], "existing": [], "skipped": [], "notes": [],
    }

    def log(line: str) -> None:
        print(line)

    vola_org_id = (settings.VOLA_ORG_ID or "").strip() or None
    if not vola_org_id:
        summary["notes"].append(
            "VOLA_ORG_ID not set in this environment — devices stored without "
            "vola_org_id; set it (Render env) and re-run, or the Vola sync will "
            "back-fill it on first poll."
        )

    async with AsyncSessionLocal() as db:
        # ── Tenant ───────────────────────────────────────────────
        tenant = await _get_scalar(
            db, select(Tenant).where(Tenant.tenant_id == TENANT_ID))
        if tenant is None:
            summary["created"].append(f"tenant:{TENANT_ID}")
            log(f"+ tenant {TENANT_ID} ({TENANT_NAME})")
            if not dry_run:
                db.add(Tenant(**build_tenant_kwargs()))
                await db.flush()
                tenant = await _get_scalar(
                    db, select(Tenant).where(Tenant.tenant_id == TENANT_ID))
        else:
            summary["existing"].append(f"tenant:{TENANT_ID}")
            log(f"= tenant {TENANT_ID} exists")
            if not dry_run and not tenant.zoho_account_id:
                tenant.zoho_account_id = ZOHO_ACCOUNT_ID
                summary["notes"].append("back-filled tenant.zoho_account_id")

        # ── Customer ─────────────────────────────────────────────
        customer = await _get_scalar(
            db,
            select(Customer).where(
                Customer.tenant_id == TENANT_ID,
                Customer.zoho_account_id == ZOHO_ACCOUNT_ID,
            ),
        )
        if customer is None:
            # fall back to name match before creating
            customer = await _get_scalar(
                db,
                select(Customer).where(
                    Customer.tenant_id == TENANT_ID,
                    Customer.name == TENANT_NAME,
                ),
            )
        customer_id = None
        if customer is None:
            summary["created"].append(f"customer:{TENANT_NAME}")
            log(f"+ customer {TENANT_NAME} (zoho {ZOHO_ACCOUNT_ID})")
            if not dry_run:
                customer = Customer(**build_customer_kwargs())
                db.add(customer)
                await db.flush()
                customer_id = customer.id
        else:
            summary["existing"].append(f"customer:{TENANT_NAME}")
            log(f"= customer {TENANT_NAME} exists")
            customer_id = customer.id
            if not dry_run and not customer.zoho_account_id:
                customer.zoho_account_id = ZOHO_ACCOUNT_ID
                summary["notes"].append("back-filled customer.zoho_account_id")

        # ── Sites ────────────────────────────────────────────────
        for spec in SITES:
            site = await _get_scalar(
                db, select(Site).where(Site.site_id == spec["site_id"]))
            if site is None:
                tag = "active" if spec["status"] == "active" else "pending"
                summary["created"].append(f"site:{spec['site_id']}")
                log(f"+ site {spec['site_id']} ({spec['site_name']}) [{tag}]")
                if not dry_run:
                    kw = build_site_kwargs(spec)
                    if customer_id is not None:
                        kw["customer_id"] = customer_id
                    db.add(Site(**kw))
                    await db.flush()
            else:
                summary["existing"].append(f"site:{spec['site_id']}")
                log(f"= site {spec['site_id']} exists (left untouched)")
                if not dry_run and customer_id is not None and site.customer_id is None:
                    site.customer_id = customer_id
                    summary["notes"].append(
                        f"back-filled customer_id on site {spec['site_id']}")

        # ── Devices ──────────────────────────────────────────────
        device_pk_by_serial: dict[str, int] = {}
        for d in DEVICES:
            dev = await _get_scalar(
                db, select(Device).where(Device.serial_number == d["serial"]))
            if dev is None:
                dev = await _get_scalar(
                    db,
                    select(Device).where(
                        Device.device_id == device_id_for(d["serial"])),
                )
            if dev is None:
                summary["created"].append(f"device:{d['serial']}")
                log(f"+ device {device_id_for(d['serial'])} "
                    f"(Elevator {d['elevator']} / IMEI {d['imei']})")
                if not dry_run:
                    obj = Device(**build_device_kwargs(d, vola_org_id=vola_org_id))
                    db.add(obj)
                    await db.flush()
                    device_pk_by_serial[d["serial"]] = obj.id
            else:
                summary["existing"].append(f"device:{d['serial']}")
                log(f"= device {d['serial']} exists (left untouched)")
                device_pk_by_serial[d["serial"]] = dev.id

        # ── Service units (elevators) ────────────────────────────
        for d in DEVICES:
            uid = unit_id_for(d["elevator"])
            su = await _get_scalar(
                db, select(ServiceUnit).where(ServiceUnit.unit_id == uid))
            if su is None:
                summary["created"].append(f"service_unit:{uid}")
                log(f"+ service_unit {uid} (Elevator {d['elevator']})")
                if not dry_run:
                    db.add(ServiceUnit(**build_service_unit_kwargs(d)))
                    await db.flush()
            else:
                summary["existing"].append(f"service_unit:{uid}")
                log(f"= service_unit {uid} exists")

        # ── SIMs + DeviceSim links ───────────────────────────────
        for d in DEVICES:
            sim = await _get_scalar(
                db, select(Sim).where(Sim.iccid == d["iccid"]))
            sim_pk = None
            if sim is None:
                summary["created"].append(f"sim:{d['iccid']}")
                log(f"+ sim {d['iccid']} (MSISDN {d['msisdn']}, T-Mobile VoLTE)")
                if not dry_run:
                    sim = Sim(**build_sim_kwargs(d))
                    db.add(sim)
                    await db.flush()
                    sim_pk = sim.id
            else:
                summary["existing"].append(f"sim:{d['iccid']}")
                log(f"= sim {d['iccid']} exists")
                sim_pk = sim.id

            dev_pk = device_pk_by_serial.get(d["serial"])
            if not dry_run and dev_pk is not None and sim_pk is not None:
                link = await _get_scalar(
                    db,
                    select(DeviceSim).where(
                        DeviceSim.device_id == dev_pk,
                        DeviceSim.sim_id == sim_pk,
                    ),
                )
                if link is None:
                    db.add(DeviceSim(
                        device_id=dev_pk, sim_id=sim_pk, slot=1,
                        active=True, assigned_by=ASSIGNED_BY,
                    ))
                    summary["created"].append(f"device_sim:{d['serial']}")
                    log(f"+ device_sim link {d['serial']} <-> {d['iccid']}")

        # ── Admin invite user ────────────────────────────────────
        email = (admin_email or os.environ.get("INTEGRITY_ADMIN_EMAIL")
                 or "admin@ipmflorida.com").strip().lower()
        if not admin_email and not os.environ.get("INTEGRITY_ADMIN_EMAIL"):
            summary["notes"].append(
                "INTEGRITY_ADMIN_EMAIL not set — defaulting admin invite to "
                f"{email}; override with INTEGRITY_ADMIN_EMAIL=<real email>.")
        existing_user = await _get_scalar(
            db, select(User).where(User.email == email))
        if existing_user is None:
            summary["created"].append(f"user:{email}")
            log(f"+ admin invite user {email} (Admin, tenant {TENANT_ID})")
            if not dry_run:
                token = generate_invite_token()
                expires = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=7)
                db.add(User(**build_admin_user_kwargs(
                    email, token,
                    hash_password(secrets.token_urlsafe(32)), expires)))
                await db.flush()
                summary["notes"].append(
                    f"invite token created for {email}; deliver the portal "
                    "invite link / accept flow out of band.")
        else:
            summary["existing"].append(f"user:{email}")
            log(f"= user {email} exists (left untouched)")

        if dry_run:
            log("\nDRY RUN — no changes committed. "
                "Re-run with DRY_RUN=false to apply.")
            await db.rollback()
        else:
            await db.commit()
            log("\nCommitted.")

    return summary


def _print_summary(summary: dict) -> None:
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for key in ("created", "existing", "skipped"):
        items = summary.get(key, [])
        print(f"  {key:9}: {len(items)}")
        for it in items:
            print(f"             - {it}")
    if summary.get("notes"):
        print("  notes:")
        for n in summary["notes"]:
            print(f"             ! {n}")


def main() -> None:
    dry_env = os.environ.get("DRY_RUN", "true").strip().lower()
    dry_run = dry_env not in ("0", "false", "no", "off")

    print("=" * 60)
    print("Integrity Property Management — Belle Terre at Sunrise onboarding")
    print("=" * 60)
    print(f"  tenant      : {TENANT_ID} ({TENANT_NAME})")
    print(f"  zoho account: {ZOHO_ACCOUNT_ID}")
    print(f"  mode        : {'DRY RUN (no writes)' if dry_run else 'APPLY (writing)'}")
    try:
        from app.config import settings
        db_url = settings.database_url if hasattr(settings, "database_url") else ""
        host = db_url.split("@")[-1].split("/")[0] if "@" in db_url else "(local)"
        print(f"  app_mode    : {getattr(settings, 'APP_MODE', '?')}")
        print(f"  db host     : {host}")
    except Exception:  # pragma: no cover - config edge
        pass
    print()

    try:
        summary = asyncio.run(apply(dry_run=dry_run))
    except Exception as exc:  # pragma: no cover - connectivity/runtime edge
        print(f"\nERROR: onboarding aborted — {type(exc).__name__}: {exc}")
        print("No changes were committed. Check DATABASE_URL / connectivity "
              "and that migrations are at head (alembic upgrade head).")
        raise SystemExit(1)
    _print_summary(summary)


if __name__ == "__main__":
    main()
