"""AI Customer Operations Center / Support Center service layer.

Pure, dependency-light building blocks for the caller-facing Tier-1
support workflow:

  * ``normalize``  — identifier normalization + phone masking.
  * ``otp``        — pluggable OTP-provider abstraction (Phase 3).
  * ``lookup``     — asset lookup by real-world identifier.
  * ``triage``     — diagnostic hooks (graceful-degrade stubs).
  * ``sessions``   — session lifecycle, OTP issue/verify, escalation.

The router (``app.routers.ops_center``) wires these to HTTP and owns the
feature-flag gate, RBAC, and tenant-context rules.
"""
