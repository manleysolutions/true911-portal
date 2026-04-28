#!/usr/bin/env python3
"""Read-only JWT decoder using the configured JWT_SECRET.

Use to confirm whether a specific token decodes cleanly on this pod.
Useful when investigating "valid login, then immediate 401" reports —
paste the user's access token and see exactly why it fails.

Run on Render shell from the api/ directory:

    cd api
    python -m scripts.decode_token --token <jwt>

Or read from stdin:

    echo "$JWT" | python -m scripts.decode_token

Read-only.  Does NOT modify any data, RBAC, or auth behavior.
The full token IS sensitive — copy/paste carefully and clear shell
history afterwards.
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

# Make `app.*` importable from either invocation form.
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from jose import JWTError, jwt  # noqa: E402

from app.config import settings  # noqa: E402


def _banner(text: str) -> None:
    print()
    print("=" * 64)
    print(text)
    print("=" * 64)


def _fmt_exp(exp) -> str:
    if exp is None:
        return "<missing>"
    try:
        ts = datetime.fromtimestamp(float(exp), tz=timezone.utc)
        delta = (ts - datetime.now(timezone.utc)).total_seconds()
        return f"{ts.isoformat()} ({delta:+.0f}s from now)"
    except (TypeError, ValueError, OverflowError):
        return f"<invalid exp={exp!r}>"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--token", default=None, help="JWT to decode.  If omitted, read from stdin.")
    args = p.parse_args()

    token = args.token
    if not token:
        token = sys.stdin.read().strip()
    if not token:
        print("ERROR: no token provided.")
        return 2

    secret = settings.JWT_SECRET or ""
    fp = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8] if secret else "<empty>"

    _banner("Configured signing context")
    print(f"  JWT_SECRET fingerprint  : {fp}")
    print(f"  JWT_ALGORITHM           : {settings.JWT_ALGORITHM}")
    print(f"  Token length            : {len(token)}")
    print(f"  Token prefix            : {token[:12]!r}...")

    # First: peek at the unverified payload (will succeed even if the
    # signature doesn't match this pod's secret) — useful for telling
    # apart "wrong secret" from "malformed token".
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError as e:
        unverified = None
        print()
        print(f"  Could not parse claims at all — token is malformed: {e}")

    if unverified is not None:
        _banner("Unverified payload (signature NOT checked)")
        print(f"  sub          : {unverified.get('sub')!r}")
        print(f"  type         : {unverified.get('type')!r}")
        print(f"  role         : {unverified.get('role')!r}")
        print(f"  tenant_id    : {unverified.get('tenant_id')!r}")
        print(f"  exp          : {_fmt_exp(unverified.get('exp'))}")
        if unverified.get("type") not in (None, "access"):
            print(
                f"  → token type is {unverified.get('type')!r}, not 'access'.  "
                "If presented as a Bearer token this would 401 with 'Invalid token type'."
            )

    # Now verify with the configured secret + algorithm.
    _banner("Verified decode (using configured JWT_SECRET)")
    try:
        verified = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as e:
        print(f"  ✗ DECODE FAILED: {type(e).__name__}: {e}")
        print()
        print("  Likely causes:")
        print("    - Token expired (compare 'exp' above with current time).")
        print("    - Token signed with a different JWT_SECRET than this pod's.")
        print("    - Token uses a different JWT_ALGORITHM.")
        print(
            "    - Token was tampered with (signature mismatch — distinct "
            "from expiry)."
        )
        return 1

    print("  ✓ DECODE OK — signature valid for this pod's JWT_SECRET")
    for k in ("sub", "type", "role", "tenant_id", "exp"):
        v = verified.get(k)
        if k == "exp":
            print(f"  {k:<12} : {_fmt_exp(v)}")
        else:
            print(f"  {k:<12} : {v!r}")
    if verified.get("type") != "access":
        print()
        print(
            f"  Note: type is {verified.get('type')!r}.  "
            "get_current_user only accepts 'access' tokens."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
