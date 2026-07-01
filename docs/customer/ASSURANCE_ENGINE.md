# True911+ — Customer Assurance Mode (Assurance Engine)

> The conceptual layer that governs what operational status a **customer** sees.
> It defines "Customer Assurance Mode" — the evidence-backed, customer-facing
> assurance label — and the **RH Login Preview** that is its first tenant-scoped
> implementation.
>
> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`
> (§4.5 explainable, §4.6 no green without evidence, §7 no jargon), `DECISIONS.md`
> (D-005 six-label vocabulary, D-006 separate axes). Companions:
> `../CUSTOMER_EXPERIENCE_BOUNDARY.md` (§F), `../CUSTOMER_DATA_BOUNDARY.md` (§6a),
> `RH_GO_LIVE_RUNBOOK.md`. Prepared: 2026-07-01.

---

## 1. What "operational status" means to a customer

The status a customer sees for a location / service / device is a **customer-facing
assurance label**, NOT a raw telemetry read. It answers one question — *"Is my
life-safety service being looked after?"* — in the six-label vocabulary (D-005):

> **Protected · Attention Needed · Critical · Pending Install · Inactive · Unknown**

This is deliberately **decoupled** from the raw operational/vendor state that
internal operators see. Internal views always render the real device/API state
(heartbeats, carrier status, reconciliation, etc.); the customer view renders an
*assurance judgment* built from evidence. The two never collapse into one number.

## 2. Evidence sources (the "Assurance Engine")

A customer-facing **Protected** must be backed by evidence (§4.6 — no green without
evidence). The engine accepts a growing set of evidence sources; today's preview
uses operator attestation, and the axis graduates to richer evidence over time:

| Evidence source | Status | Notes |
|---|---|---|
| **Live telemetry** (heartbeat/health) | target | the strongest signal; the Assurance engine already computes labels from it |
| **Carrier status** (line/activation state) | planned | carrier/vendor adapter reports |
| **Installer verification** | planned | field installer confirms install + test |
| **Customer verification** | planned | customer confirms the endpoint works |
| **Manual operations verification** | **live (preview)** | Manley operator attests the service is active — the RH preview bridge |
| **Last successful test** (test call / self-test) | partial | already contributes to the site assurance evidence |
| **AI confidence scoring** | future | weighs the above into a confidence-graded label |

**Preview = operator-attestation evidence.** Until live telemetry is connected, an
allow-listed tenant's operational axis is presented as **Protected** carrying an
honest operator-attestation signal (`"Service active — confirmed by Manley
Solutions"`, `source: operator`). It is **not** fabricated telemetry (never "N
devices reporting", never a fake `last_seen`) and is deliberately free of any
"API pending" / "telemetry pending" language. As a real evidence source (telemetry,
carrier, test) arrives for a location, it **supersedes** the attestation and the
preview is retired for that location (see §5).

## 3. E911 is excluded — always the truth

The **E911 axis is safety-critical and is NEVER preview-overridden.** Emergency-
address verification is derived *only* from the stored record
(`Site.e911_status ∈ {validated, verified}`), enumerated per endpoint from real
`ServiceUnit` + linked `Line.did` / `Device.msisdn` data ("where applicable", never
fabricated). An active location with an unverified address is shown **Critical**,
never green — even while its operational axis is a preview **Protected** (D-006:
the axes never collapse). Missing/unverified E911 is surfaced **internally** for
correction via `GET /api/e911-changes/gaps` and the readiness check.

## 4. Internal views are unchanged

Customer Assurance Mode is **presentation-only**. It writes nothing and mutates no
raw state. Internal / admin / operator views (`/command/*`, the Assurance engine,
device health) read the **real** operational and vendor state and are completely
unaffected. The customer's assurance label and the operator's raw status are two
separate renderings of the same underlying (untouched) data.

## 5. RH Login Preview — the first tenant-scoped implementation

Restoration Hardware is the first tenant to run Customer Assurance Mode, via a
two-key gate mirroring the customer API (default **OFF** everywhere):

```
FEATURE_CUSTOMER_PREVIEW == "true"  AND  <tenant> ∈ CUSTOMER_PREVIEW_TENANT_ALLOWLIST
```

Code: `api/app/services/customer/preview.py` (gate + evidenced green),
`portfolio.py` / `serialize.py` (composition), `routers/customer.py` (the
`/api/customer/*` surface the customer UI reads). The isolated `CUSTOMER_*` roles
consume this API — they hold no `INTERNAL_OPS` grant and cannot reach internal
routes.

## 6. Rollback

Instant, no deploy / migration / data change:

1. **Per tenant:** remove the tenant from `CUSTOMER_PREVIEW_TENANT_ALLOWLIST` →
   operational status reverts to the real assurance labels (Unknown/Pending until
   telemetry lands). E911 is unaffected (it was always real).
2. **Global:** set `FEATURE_CUSTOMER_PREVIEW=false` (api **and** worker) → preview
   off everywhere.
3. **Retire per location (graduation, not rollback):** as live telemetry / carrier
   / test evidence arrives for a location, that evidence supersedes the operator
   attestation automatically; drop the tenant from the allow-list once enough
   locations report to stand on real evidence alone.

Because the mode is presentation-only, rollback loses no data and corrupts no
source-of-truth axis.
