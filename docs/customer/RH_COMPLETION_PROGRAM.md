# RH Customer Completion Program

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`,
> `DECISIONS.md` D-023, D-024, D-025. Approved 2026-09-30.

**Objective:** make Restoration Hardware the **reference customer implementation**
for True911. Judy is **not** invited until RH is operationally trustworthy end to
end; the canonical customer read model is **not** enabled for Judy before then.
Generalisation to other customers ("Customer Portfolio Certification") happens
only after RH is READY_FOR_CUSTOMER and launched.

## 1. Definition of done (RH ready for Judy)

1. Every current RH building represented exactly once.
2. Historical / closed / duplicate buildings preserved internally, never shown as
   current customer locations.
3. Every current life-safety service reconciled.
4. Every required communications connection represented correctly.
5. Every communications asset associated with the correct building/service or
   explicitly classified non-life-safety / unresolved.
6. E911 provisioned and verified for every applicable line (or an approved launch
   exception, §4).
7. Every current building has a validated canonical address.
8. Every current building has validated latitude / longitude.
9. Customer map: exactly one marker per current canonical building.
10. No known duplicate / contaminated identity exposed to Judy.
11. No customer-visible metric presents PROBABLE / UNRESOLVED evidence as confirmed.
12. RH Test passes a complete customer acceptance test.
13. Final RH launch audit has zero BLOCKERS.
14. Only then a **fresh** Judy invitation is generated (the existing invitation and
    any token ever exposed are invalid for launch).

Never fabricate missing facts to satisfy a gate. **45 is not a target**: it is
today's approved registry count. Edina and Raleigh carry evidence of additional
real locations and merges may reduce others — the final count is whatever the
certified physical portfolio contains.

## 2. PR sequence

> **Program slots are not GitHub PR numbers.** "#187–#193" below name the
> program's slots. GitHub PR numbers are assigned independently: GitHub #189–#193
> were unrelated PRs, and #187 happened to match its slot. **Migration numbering
> corrected 2026-10-02:** migration `056` was used by GitHub PR #198 (acquisition
> records), so the program's remaining migrations start at **057**. Always confirm
> the current single Alembic head before numbering a new migration.

| Program slot | Scope | Migration |
|---|---|---|
| #187 | Source snapshot store + importers (NAPCO, T-Mobile/Infatrac, Verizon, Red Pocket) — `SOURCE_SNAPSHOTS.md` | 055 (merged) |
| #188 | Lifecycle + carrier reconciliation; Jacksonville decisions previewed then recorded with explicit operator authorisation | 057 (was 056) |
| #189 | RH building certification + identity cleanup | 058 (was 057) |
| #190 | Canonical geocoding (internal) | 059 (was 058) |
| #191 | E911 completion + safety corrections | 060 (was 059) |
| #192 | Canonical customer read model + map (flag-gated) | 061 (was 060) |
| #193 | RH customer acceptance gate + final UX | — |

Each PR starts from updated `main`, is independently reviewable and
rollback-safe, preserves human decisions and E911 integrity, never commits
production exports or identifiers, never writes external systems.

**Baseline** (first untouched #186a production dry-run, Zoho healthy, active
operator decisions = 0): 45 approved buildings; confirmed/current FACP 9, ELEVATOR
17, EMERGENCY_PHONE 0; confirmed services 26; required confirmed connections 35;
probable services 13 (+17 probable connections); unresolved life-safety services 9;
unclassified current lines 13; unplaced numbers 3; historical assets 41.
Conservative by design — never forced toward a target.

## 3. Recorded decisions (so implementation does not drift)

### Jacksonville (#188)
Operator knowledge is **not yet** persisted (production `operator_decisions
active=0`). Ground truth: six legacy Red Pocket lines replaced/decommissioned;
seven replacement T-Mobile lines current; exactly two are Elevators; five Voice
lines stay UNCLASSIFIED (no guessing emergency / desk / fax). #188 reconciles
source evidence, **previews** the proposed decisions, requires **explicit operator
authorisation**, records them through the governed decision ledger and preserves
the six old lines as historical lineage. Operator knowledge is never encoded as an
engine rule.

### Source evidence (#187/#188)
Carrier ACTIVE may establish CURRENT asset lifecycle but never a service type.
NAPCO ACTIVE may establish CURRENT for a deterministically matched FACP
communicator/service but never FACP health, monitoring or E911. Absence from one
carrier never establishes decommissioning. Freshness (7 days) is inventory
certification only.

### E911 applicability (#191) — product policy, not a legal conclusion
| Line | E911 assessment |
|---|---|
| Elevator voice line | REQUIRED |
| Emergency phone | REQUIRED |
| Other current voice-capable line | REQUIRED until positively classified |
| Fax-only | NOT_REQUIRED only after positive classification |
| Data-only | NOT_REQUIRED only after positive classification |
| FACP / NAPCO communicator paths | not modelled as E911 telephone lines merely because they are required life-safety paths |

Every NOT_REQUIRED keeps its reason and evidence. Not hard-coded as applicable to
every deployment or jurisdiction.

### E911 verification (#191)
Legacy True911 "validated" / "confirmed" is **not** sufficient for canonical
VERIFIED, which requires authoritative provider/provisioning evidence. Verified
counts may drop — expected; no incorrect green is preserved. Safety fixes: one
canonical VERIFIED definition; "confirmed" ≠ verified; changing an E911 address
resets verification; one customer vocabulary.

### E911 launch exception (#191/#193)
Only **SUPER_ADMIN** may approve `E911_LAUNCH_EXCEPTION`. Requires approver,
reason, evidence/reference, created_at, expires_at; default and maximum initial
expiry **30 days**. An exception never becomes VERIFIED and is always
distinguishable from authoritative verification.

### Geocoding (#190)
Only the canonical **certified** building address. Never billing address, parent
account, headquarters, carrier location, device GPS or an arbitrary linked Site. A
building's address/identity must be CERTIFIED before its coordinates can be
VALIDATED. US auto-validation: deterministic normalisation + Nominatim / US Census
agreement under the strict rules. Canada and ambiguous / special addresses go to
operator review unless an equally defensible deterministic rule is established.

### Monitoring
Part of the eventual acceptance model but not a #187 rewrite. NAPCO ACTIVE / last
signal are communicator evidence, not proof of central-station enrolment, healthy
FACP, a recent test, E911 or complete protection. Monitoring-source gaps are
carried as explicit certification findings; nothing claims "Monitored" without
authoritative evidence.

### RH Test
A deliberate permanent customer-perspective QA account; production has used
`test@manleysolutions.com`. Do not create a duplicate. Before #193: verify in
production its tenant, active state, CUSTOMER_ADMIN (or intended test) role and
allowlist, then use it for the full walkthrough.

## 4. READY_FOR_CUSTOMER gate (#193) — approved, minimum

* **Portfolio:** every current RH building certified; no duplicate current
  canonical buildings; no unresolved current-building identity conflicts.
* **Services:** no probable/unresolved life-safety service exposed as confirmed;
  unresolved services carry an explicit operator disposition.
* **Assets:** no unplaced CURRENT communications assets; carrier/source conflicts
  resolved or dispositioned; historical assets excluded from current inventory.
* **E911:** every applicable current line VERIFIED, or covered by an explicit,
  unexpired SUPER_ADMIN launch exception; exceptions never display as VERIFIED.
* **Map:** every current customer-visible building has validated coordinates;
  exactly one marker per canonical building; map/list/detail IDs agree.
* **Freshness:** canonical projection fresh and non-degraded; required source
  snapshots fresh.
* **Customer model:** one canonical read model feeds dashboard / list / map /
  detail / services / actions; counts reconcile; no false "connections"; nothing
  probable/unresolved presented as confirmed; no composite health score; UNKNOWN is
  neither FAILED nor PROTECTED / MONITORED.
* **RH Test:** automated checks pass; CUSTOMER_ADMIN security tests pass; manual
  customer-perspective walkthrough recorded.

Verdict ladder: BLOCKED → READY_FOR_INTERNAL_QA → READY_FOR_RH_TEST →
READY_FOR_CUSTOMER, then explicit operator approval, then a fresh invitation.
