# True911+ — DECISIONS LOG

> Append-only record of every architectural, business, workflow, and philosophy
> decision. **Never edit or delete a past entry** — supersede it with a new one
> (`Status: Superseded by D-NNN`). Required by `CONSTITUTION.md` P2/P3. Entry IDs
> are stable and referenced from other documents.

| Metadata | |
|---|---|
| **Authority Level** | 2 — Architecture (canonical, immutable record) |
| **Owner** | Product Owner + Principal Architect |
| **Last Reviewed** | 2026-06-14 |
| **Change Frequency** | Append-only (frequent additions; entries never edited) |
| **Status** | Active — D-001 … D-011 recorded; latest ID: D-011 |
| **Governed By** | `CONSTITUTION.md` |
| **Detailed In** | the document each decision affects |
| **Related Decisions** | — |

**Entry format:** ID · Date · Status (Accepted / Superseded / Reversed) · Context ·
Decision · Consequences.

---

### D-001 — Adopt the constitutional rules P1–P5
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** Load-bearing knowledge was accumulating only in conversation; no
  formal governance existed for documentation or slice size.
- **Decision:** Adopt P1 Single Source of Truth, P2 Documentation Freshness, P3 No
  Conversation Dependency, P4 AI Session Rule, P5 Smallest Safe Slice
  (`CONSTITUTION.md` §5).
- **Consequences:** All future work follows these rules; `OPERATING_LOOP.md`
  enforces them; this log becomes mandatory.

### D-002 — Defer T-Mobile PIT private-key rotation (accepted PIT-only risk)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** An RSA private key was committed to git history (BACKLOG C1). Repo
  cleanup merged (PR #112); history rewrite is approval-gated and out of scope.
- **Decision:** Treat the key as a PIT/testing-only credential and **defer
  rotation** while the integration stays in PIT, tracking mandatory rotation as the
  C3 pre-production gate.
- **Consequences:** Key in history remains compromised; must rotate before any
  production/external/customer/gov exposure. See `TMOBILE_PRIVATE_KEY_REMEDIATION.md`.

### D-003 — C3 pre-production gate (hard go-live blocker)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** The D-002 deferral is safe only within PIT.
- **Decision:** Rotation of the T-Mobile key is a hard gate before external
  evaluators, customer pilots, production traffic, carrier certification, or
  gov/customer demos.
- **Consequences:** `TMOBILE_ENV=prod` / live calls for a real account are blocked
  until closed.

### D-004 — Customer label wording: "Protected (as of <time>) + disclaimer"
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** "911 Ready" risked reading as a guarantee (liability).
- **Decision:** Customer string is **"Protected"** with an "as of" timestamp +
  disclaimer; internal/clinical equivalent "Active & Verified." No guarantee 911
  will connect (`CONSTITUTION.md` §7.3).
- **Consequences:** All assurance surfaces use this wording. Detail in
  `ASSURANCE_ENGINE.md`.

### D-005 — Six-label assurance vocabulary
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Protected · Attention Needed · Critical · Pending Install ·
  Inactive/Deactivated · Unknown. No customer-facing numeric score
  (`CONSTITUTION.md` §7.1).
- **Consequences:** Fixed vocabulary across all surfaces; detail in
  `ASSURANCE_PLATFORM_SPEC.md` / `ASSURANCE_ENGINE.md`.

### D-006 — Separate-axes invariant
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Operational, commercial-lifecycle, E911/compliance, and
  deployment-lifecycle are separate axes with one owner each; reads compose, writes
  never overwrite another axis. Missing data ≠ healthy.
- **Consequences:** Constitutional (`CONSTITUTION.md` §4.3); enforced in
  `DATA_MODEL.md` and the Assurance/Truth engines.

### D-007 — Truth Engine is read-only-first; event bus deferred
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Build the Truth Engine resolve-and-report (shadow) before
  resolve-and-write; defer a true event bus until write-time resolution is proven.
- **Consequences:** First slice writes nothing; everything flag-gated
  (`FEATURE_TRUTH_ENGINE`). See `TRUTH_ENGINE.md`.

### D-008 — CI secret scanning via gitleaks in working-tree mode (CI-1A)
- **Date:** 2026-06-14 · **Status:** Accepted
- **Context:** No secret scanning existed (the gap behind C1).
- **Decision:** Add a blocking gitleaks job using **`gitleaks dir`** (working-tree),
  not history mode (which would re-flag the accepted C1 key), via a pinned binary
  (avoids the org-license requirement), with a tuned `.gitleaks.toml` allowlist.
- **Consequences:** PR #116. No file type blanket-excluded; verified to block on
  planted `.pem`/`.env`/`.key`/PAT secrets.

### D-009 — Documentation migration as two grouped doc-only PRs
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Establish the DocOS via PR A (new governing docs) + PR B (integrate
  existing docs). Documentation-only; preserve history; cross-reference not copy.
- **Consequences:** This document set; `PRODUCT_MANIFESTO.md` promoted to
  `CONSTITUTION.md` via `git mv`.

### D-010 — Four-level Documentation Operating System
- **Date:** 2026-06-14 · **Status:** Accepted
- **Decision:** Adopt the four-level authority hierarchy (Governance / Architecture
  / Execution / Process) with `README.md` as the required entry point and the
  North Star (in `PRODUCT_VISION.md`) as the success statement.
- **Consequences:** See `README.md`; authority flows top-down; conflicts resolved by
  level then by the priority order.

### D-011 — Phase 0 / PR-1 scope: read-only Identity Resolution Audit
- **Date:** 2026-06-14 · **Status:** Accepted (plan)
- **Decision:** First Truth Engine slice = pure `IdentityResolver` + read-only audit
  + SuperAdmin endpoint behind `FEATURE_TRUTH_ENGINE`; no writes, no migration, no
  frontend, no `permissions.json` change (reuse `GLOBAL_ADMIN`). Recommended split:
  PR-1a pure resolver + tests, then PR-1b audit + endpoint.
- **Consequences:** Implementation pending approval. Design in `TRUTH_ENGINE.md`.
