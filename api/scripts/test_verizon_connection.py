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
        _print_result("Base URL", data.get("base_url", "?"))
        _print_result("Account name", data.get("account_name", "(not set)"))
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
        _print_result("Message", data.get("message", "?"), ok)

        if data.get("account_name"):
            _print_result("Account", data["account_name"])
        if data.get("note"):
            _print_result("Note", data["note"], False)
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

    print()


if __name__ == "__main__":
    main()
