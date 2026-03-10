#!/usr/bin/env python3
"""Test Verizon ThingSpace integration via the True911 API.

Authenticates as an admin user, then calls the Verizon carrier endpoints
to verify configuration and connectivity.

Environment variables:
    TRUE911_API_URL       — base URL (default: http://localhost:8000)
    TRUE911_ADMIN_EMAIL   — admin email for login
    TRUE911_ADMIN_PASSWORD — admin password for login

Usage:
    cd api/
    python scripts/test_verizon_connection.py
"""

import json
import os
import sys
import time

import httpx

# ── Config from env ──────────────────────────────────────────────────────

API_URL = os.environ.get("TRUE911_API_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("TRUE911_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TRUE911_ADMIN_PASSWORD", "")

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _redact(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 6:
        return "***"
    return value[:3] + "***" + value[-3:]


def _sanitize_payload(data: dict) -> dict:
    """Remove or redact sensitive fields from a response payload for printing."""
    sensitive_keys = {
        "access_token", "refresh_token", "token", "sessionToken",
        "password", "secret", "api_key", "api_secret",
    }
    sanitized = {}
    for k, v in data.items():
        if k.lower() in {s.lower() for s in sensitive_keys}:
            sanitized[k] = _redact(str(v)) if v else "(empty)"
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_payload(v)
        else:
            sanitized[k] = v
    return sanitized


def _print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _print_result(label: str, value: str, ok: bool = True):
    marker = "[OK]" if ok else "[!!]"
    print(f"  {marker} {label}: {value}")


def _print_json(data: dict, indent: int = 4):
    print(json.dumps(data, indent=indent, default=str))


# ── Step 1: Health check ─────────────────────────────────────────────────

def check_health(client: httpx.Client) -> bool:
    _print_section("Step 1: API Health Check")
    try:
        resp = client.get(f"{API_URL}/api/health")
        _print_result("URL", API_URL)
        _print_result("HTTP status", str(resp.status_code), resp.status_code == 200)
        if resp.status_code == 200:
            data = resp.json()
            _print_result("API status", data.get("status", "?"))
            _print_result("App mode", data.get("app_mode", "?"))
            return True
        else:
            _print_result("Response", resp.text[:200], False)
            return False
    except httpx.ConnectError as e:
        _print_result("Connection", f"FAILED — is the API running at {API_URL}?", False)
        _print_result("Error", str(e)[:200], False)
        return False


# ── Step 2: Login ────────────────────────────────────────────────────────

def login(client: httpx.Client) -> str | None:
    _print_section("Step 2: Admin Login")

    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        _print_result("Credentials", "NOT SET — set TRUE911_ADMIN_EMAIL and TRUE911_ADMIN_PASSWORD", False)
        return None

    _print_result("Email", ADMIN_EMAIL)
    _print_result("Password", _redact(ADMIN_PASSWORD))

    resp = client.post(
        f"{API_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )

    _print_result("HTTP status", str(resp.status_code), resp.status_code == 200)

    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access_token", "")
        user = data.get("user", {})
        _print_result("Token acquired", "YES" if token else "NO", bool(token))
        _print_result("User", f"{user.get('name', '?')} ({user.get('email', '?')})")
        _print_result("Role", user.get("role", "?"))
        _print_result("Tenant", user.get("tenant_id", "?"))
        return token
    else:
        try:
            err = resp.json()
            _print_result("Error", err.get("detail", resp.text[:200]), False)
        except Exception:
            _print_result("Error", resp.text[:200], False)
        return None


# ── Step 3: Verizon config ───────────────────────────────────────────────

def check_verizon_config(client: httpx.Client, token: str) -> dict | None:
    _print_section("Step 3: Verizon Config Check")

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"{API_URL}/api/carriers/verizon/config", headers=headers)

    _print_result("HTTP status", str(resp.status_code), resp.status_code == 200)

    if resp.status_code == 200:
        data = resp.json()
        _print_result("Auth mode", data.get("auth_mode", "(not set)"))
        m2m_mode = data.get("m2m_auth_mode", "(n/a)")
        if m2m_mode and m2m_mode != "(n/a)":
            _print_result("M2M auth mode", m2m_mode)
        _print_result("Base URL", data.get("base_url", "?"))
        if data.get("oauth_token_url"):
            _print_result("OAuth token URL", data["oauth_token_url"])
        if data.get("m2m_session_login_url"):
            _print_result("M2M session login URL", data["m2m_session_login_url"])
        if data.get("m2m_session_credentials_set") is not None:
            _print_result(
                "Session credentials set",
                "YES" if data["m2m_session_credentials_set"] else "NO",
                data["m2m_session_credentials_set"],
            )
        if data.get("app_token_header") and data["app_token_header"] != "(n/a)":
            _print_result("App token header", data["app_token_header"])
        _print_result("Account name", data.get("account_name", "(not set)"))
        m2m_acct = data.get("m2m_account_id", "(n/a)")
        if m2m_acct and m2m_acct != "(not set — using account_name)":
            _print_result("M2M account ID", m2m_acct)
        _print_result("Configured", str(data.get("is_configured", False)), data.get("is_configured", False))

        if not data.get("is_configured"):
            if data.get("error"):
                _print_result("Error", data["error"], False)
            if data.get("missing_vars"):
                _print_result("Missing vars", ", ".join(data["missing_vars"]), False)

        return data
    else:
        try:
            err = resp.json()
            _print_result("Error", err.get("detail", resp.text[:200]), False)
        except Exception:
            _print_result("Error", resp.text[:200], False)
        return None


# ── Step 4: Verizon connection test ──────────────────────────────────────

def test_verizon_connection(client: httpx.Client, token: str) -> dict | None:
    _print_section("Step 4: Verizon Connection Test")

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(f"{API_URL}/api/carriers/verizon/test-connection", headers=headers)

    _print_result("HTTP status", str(resp.status_code), resp.status_code == 200)

    if resp.status_code == 200:
        data = resp.json()
        ok = data.get("ok", False)
        _print_result("Connection OK", str(ok), ok)
        _print_result("Auth mode", data.get("auth_mode", "?"))
        if data.get("m2m_auth_mode"):
            _print_result("M2M auth mode", data["m2m_auth_mode"])
        if data.get("oauth_token_url"):
            _print_result("OAuth token URL", data["oauth_token_url"])
        if data.get("oauth_token_obtained") is not None:
            _print_result(
                "OAuth token obtained",
                "YES" if data["oauth_token_obtained"] else "NO",
                data["oauth_token_obtained"],
            )
        if data.get("oauth_token_status"):
            _print_result("OAuth token HTTP", str(data["oauth_token_status"]), False)
        if data.get("oauth_token_body"):
            _print_result("OAuth token body", data["oauth_token_body"][:300], False)
        if data.get("m2m_session_login_url"):
            _print_result("M2M session login URL", data["m2m_session_login_url"])
        if data.get("m2m_session_token_obtained") is not None:
            _print_result(
                "M2M session token obtained",
                "YES" if data["m2m_session_token_obtained"] else "NO",
                data["m2m_session_token_obtained"],
            )
        if data.get("m2m_session_login_status"):
            _print_result("M2M session login HTTP", str(data["m2m_session_login_status"]), False)
        if data.get("m2m_session_login_body"):
            _print_result("M2M session login body", data["m2m_session_login_body"][:300], False)
        if data.get("token_type"):
            _print_result("Token type", data["token_type"])
        if data.get("request_headers_sent"):
            _print_result("Headers sent", ", ".join(data["request_headers_sent"]))
        _print_result("Message", data.get("message", "?"), ok)

        if data.get("account_name"):
            _print_result("Account", data["account_name"])
        if data.get("m2m_account_id"):
            _print_result("M2M account ID", data["m2m_account_id"])
        if data.get("note"):
            _print_result("Note", data["note"], False)
        if data.get("account_info_endpoint"):
            _print_result("Acct endpoint", data["account_info_endpoint"], False)
        if data.get("account_info_status"):
            _print_result("Acct endpoint HTTP", str(data["account_info_status"]), False)
        if data.get("account_info_body"):
            _print_result("Acct endpoint body", data["account_info_body"][:300], False)

        # M2M request-level diagnostics (shows exact outbound request details)
        if data.get("m2m_request_method"):
            print("\n  M2M Request Diagnostics:")
            _print_result("  M2M method", data["m2m_request_method"], False)
            _print_result("  M2M URL", data.get("m2m_request_url", "?"), False)
            _print_result("  Intended headers", ", ".join(data.get("m2m_request_headers", [])), False)
            actual = data.get("m2m_actual_headers_sent")
            if actual:
                _print_result("  Actual wire headers", ", ".join(actual), False)
                # Flag mismatch between intended and actual
                intended_set = set(data.get("m2m_request_headers", []))
                actual_set = set(actual)
                if intended_set != actual_set:
                    _print_result("  HEADER MISMATCH", f"intended={intended_set - actual_set} actual_extra={actual_set - intended_set}", False)
            if data.get("m2m_request_params"):
                _print_result("  Query params", ", ".join(data["m2m_request_params"]), False)
            if data.get("m2m_request_body_keys"):
                _print_result("  Body keys", ", ".join(data["m2m_request_body_keys"]), False)

        if data.get("account_info"):
            print("\n  Account info (sanitized):")
            _print_json(_sanitize_payload(data["account_info"]))

        return data
    else:
        try:
            err = resp.json()
            _print_result("Error", err.get("detail", resp.text[:300]), False)
        except Exception:
            _print_result("Raw response", resp.text[:300], False)

        # Print headers for debugging (no auth headers)
        safe_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("authorization", "set-cookie")
        }
        print("\n  Response headers:")
        for k, v in safe_headers.items():
            print(f"    {k}: {v}")

        return None


# ── Step 5: Device preview ───────────────────────────────────────────────

def preview_verizon_devices(client: httpx.Client, token: str, display: int = 5) -> dict | None:
    # Verizon requires maxNumberOfDevices between 500 and 2000.
    # We request the minimum (500) from our API, then display only the
    # first `display` devices in the test output.
    _print_section(f"Step 5: Verizon Device Preview (showing first {display})")

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(
        f"{API_URL}/api/carriers/verizon/devices",
        params={"max_results": 500},
        headers=headers,
    )

    _print_result("HTTP status", str(resp.status_code), resp.status_code == 200)

    if resp.status_code == 200:
        data = resp.json()
        total = data.get("total", 0)
        devices = data.get("devices", [])
        _print_result("Devices returned (from Verizon)", str(total), total > 0)
        _print_result("Showing first", str(min(display, total)))

        if devices:
            d = devices[0]
            print("\n  First device (normalized):")
            _print_result("  carrier", d.get("carrier", "?"))
            _print_result("  external_id", d.get("external_id") or "(none)")
            _print_result("  imei", d.get("imei") or "(none)")
            _print_result("  iccid", d.get("iccid") or "(none)")
            _print_result("  msisdn", d.get("msisdn") or "(none)")
            _print_result("  sim_status", d.get("sim_status") or "(none)")
            _print_result("  line_status", d.get("line_status") or "(none)")
            _print_result("  activation_status", d.get("activation_status") or "(none)")
            _print_result("  last_seen_at", d.get("last_seen_at") or "(none)")
            usage = d.get("usage_data_mb")
            _print_result("  usage_data_mb", str(usage) if usage is not None else "(none)")

            if total > 1:
                print(f"\n  ... plus {total - 1} more device(s)")
        else:
            _print_result("Devices", "API returned 0 devices", False)

        return data
    else:
        try:
            err = resp.json()
            detail = err.get("detail", resp.text[:300])
            # If detail is a dict (structured error), show it nicely
            if isinstance(detail, dict):
                _print_result("Error", detail.get("error", "?"), False)
                if detail.get("body"):
                    _print_result("Verizon body", str(detail["body"])[:300], False)
                if detail.get("request_method"):
                    _print_result("Request", f"{detail['request_method']} {detail.get('request_url', '?')}", False)
                if detail.get("request_headers"):
                    _print_result("Intended headers", ", ".join(detail["request_headers"]), False)
                if detail.get("actual_headers_sent"):
                    _print_result("Actual wire headers", ", ".join(detail["actual_headers_sent"]), False)
                if detail.get("request_body_keys"):
                    _print_result("Body keys", ", ".join(detail["request_body_keys"]), False)
            else:
                _print_result("Error", str(detail)[:300], False)
        except Exception:
            _print_result("Raw response", resp.text[:300], False)

        return None


# ── Step 6: Dry-run sync ─────────────────────────────────────────────────

def dry_run_sync(client: httpx.Client, token: str) -> dict | None:
    _print_section("Step 6: Dry-Run Sync (safe — no DB writes)")

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        f"{API_URL}/api/carriers/verizon/sync",
        params={"dry_run": "true", "max_results": 500},
        headers=headers,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )

    _print_result("HTTP status", str(resp.status_code), resp.status_code == 200)

    if resp.status_code == 200:
        data = resp.json()
        _print_result("Mode", "DRY-RUN (nothing persisted)", True)
        _print_result("Tenant", data.get("tenant_id", "?"))
        _print_result("Total fetched from Verizon", str(data.get("total_fetched", 0)))
        _print_result("Would create", str(data.get("created", 0)))
        _print_result("Would update", str(data.get("updated", 0)))
        _print_result("Unchanged", str(data.get("unchanged", 0)))
        _print_result("Skipped", str(data.get("skipped", 0)))

        conflicts = data.get("conflicts", [])
        if conflicts:
            _print_result("CONFLICTS", str(len(conflicts)), False)
            for c in conflicts[:10]:
                ctype = c.get("type", "?")
                if ctype == "iccid_cross_tenant":
                    print(f"    ICCID {c.get('iccid')} owned by tenant "
                          f"'{c.get('existing_tenant_id')}' (not yours)")
                elif ctype == "msisdn_collision":
                    print(f"    MSISDN {c.get('msisdn')} already on ICCID "
                          f"{c.get('existing_iccid')} (incoming: {c.get('iccid')})")
                elif ctype == "msisdn_batch_duplicate":
                    print(f"    MSISDN {c.get('msisdn')} duplicated in batch: "
                          f"{c.get('first_iccid')} vs {c.get('iccid')}")
                else:
                    print(f"    {c}")
            if len(conflicts) > 10:
                print(f"    ... plus {len(conflicts) - 10} more")
        else:
            _print_result("Conflicts", "0 (clean)", True)

        # Show first few detail actions
        details = data.get("details", [])
        if details:
            creates = [d for d in details if d.get("action") == "create"]
            updates = [d for d in details if d.get("action") == "update"]
            skips = [d for d in details if d.get("action") == "skip"]

            if creates:
                print(f"\n  Sample creates (first 3 of {len(creates)}):")
                for d in creates[:3]:
                    print(f"    ICCID={d.get('iccid')}  MSISDN={d.get('msisdn') or '(none)'}  "
                          f"status={d.get('status', '?')}")

            if updates:
                print(f"\n  Sample updates (first 3 of {len(updates)}):")
                for d in updates[:3]:
                    changes = d.get("changes", {})
                    parts = [f"{k}: {v[0]} -> {v[1]}" for k, v in changes.items()]
                    print(f"    ICCID={d.get('iccid')}  {', '.join(parts)}")

            if skips:
                print(f"\n  Skipped ({len(skips)}):")
                for d in skips[:5]:
                    print(f"    ICCID={d.get('iccid', '?')}  reason={d.get('reason', '?')}")

        return data
    else:
        try:
            err = resp.json()
            detail = err.get("detail", resp.text[:300])
            if isinstance(detail, dict):
                _print_result("Error", detail.get("error", "?"), False)
            else:
                _print_result("Error", str(detail)[:300], False)
        except Exception:
            _print_result("Raw response", resp.text[:300], False)
        return None


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("\n  True911 Verizon ThingSpace Integration Test")
    print(f"  Target: {API_URL}")
    print(f"  Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    with httpx.Client(timeout=TIMEOUT) as client:
        # Step 1: Health
        if not check_health(client):
            print("\n  ABORT: API is not reachable. Start the server first.")
            sys.exit(1)

        # Step 2: Login
        token = login(client)
        if not token:
            print("\n  ABORT: Could not obtain auth token. Check credentials.")
            sys.exit(1)

        # Step 3: Config
        config = check_verizon_config(client, token)

        # Step 4: Connection test
        result = test_verizon_connection(client, token)

        # Step 5: Device preview (only if connection succeeded)
        devices = None
        if result and result.get("ok"):
            devices = preview_verizon_devices(client, token)

        # Step 6: Dry-run sync (only if devices were fetched)
        sync_result = None
        if devices and devices.get("total", 0) > 0:
            sync_result = dry_run_sync(client, token)

    # Summary
    _print_section("Summary")
    _print_result("API reachable", "YES")
    _print_result("Auth token", "YES")

    if config:
        is_cfg = config.get("is_configured", False)
        _print_result("Verizon configured", str(is_cfg), is_cfg)
    else:
        _print_result("Verizon configured", "UNKNOWN", False)

    if result:
        ok = result.get("ok", False)
        _print_result("Verizon connected", str(ok), ok)
        if not ok:
            print(f"\n  Next step: Check your VERIZON_THINGSPACE_* env vars in api/.env")
            print(f"  Current auth mode: {config.get('auth_mode', '(not set)')}")
            if config and config.get("missing_vars"):
                print(f"  Missing: {', '.join(config['missing_vars'])}")
    else:
        _print_result("Verizon connected", "FAILED", False)

    if devices:
        total = devices.get("total", 0)
        _print_result("Devices fetched", str(total), total > 0)
    elif result and result.get("ok"):
        _print_result("Devices fetched", "FAILED", False)

    if sync_result:
        conflicts = sync_result.get("conflicts", [])
        safe = len(conflicts) == 0
        _print_result(
            "Dry-run sync",
            f"create={sync_result.get('created', 0)} "
            f"update={sync_result.get('updated', 0)} "
            f"skip={sync_result.get('skipped', 0)} "
            f"conflicts={len(conflicts)}",
            safe,
        )
        if safe:
            _print_result("READY FOR LIVE SYNC", "Yes — 0 conflicts detected", True)
        else:
            _print_result("LIVE SYNC BLOCKED", f"{len(conflicts)} conflict(s) must be resolved first", False)

    print()


if __name__ == "__main__":
    main()
