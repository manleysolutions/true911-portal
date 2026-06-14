# True911+ — OPERATING LOOP

> Living document. This is the discipline every development session must follow.
> It is deliberately heavyweight because True911 is a life-safety platform.
> Last reviewed: 2026-06-14.
>
> **Authority Level:** 4 — Process. **Governed by:** `CONSTITUTION.md`. This
> document operationalizes the constitutional rules P1–P5; it does not redefine
> them (`CONSTITUTION.md` §5).

## 0. Before You Touch Anything — AI Session Rule (`CONSTITUTION.md` P4)

Start every session at **`README.md`** (the documentation entry point), then in
order:

1. Read `docs/CONSTITUTION.md` (principles + priority order + P1–P5).
2. Read `docs/DECISIONS.md` (what was already decided, and why).
3. Read `docs/PROJECT_STATE.md` (current objective, in-flight, blockers, risks).
4. Read `docs/MASTER_PLAN.md` (where this fits) and `docs/BACKLOG.md` (priorities).
5. Build a dependency graph for the task.
6. Plan → **wait for approval** → implement in the **smallest safe slice** (P5).
7. Confirm the working branch and that `git status` is clean before starting.

The **priority order** in `CONSTITUTION.md` §3 is the tiebreaker for every decision
below.

## 0a. Governance Gates (enforce on every change)

- **P1 — Single Source of Truth:** put each new fact in exactly one doc; reference,
  never copy.
- **P2 — Documentation Freshness:** a change is not done until docs +
  `PROJECT_STATE.md` are updated and any decision is recorded in `DECISIONS.md`.
- **P3 — No Conversation Dependency:** before any work depends on a decision, rule,
  workflow, or design, confirm it is written in the correct doc; if it exists only
  in chat, write it first.
- **P5 — Smallest Safe Slice:** decompose until each slice is independently
  reviewable, testable, and reversible.

## 0b. Data Steward Workflow

The Data Steward operates `Import → Validate → Reconcile → Approve → Publish`
(detail: `TRUTH_ENGINE.md` §10) — owning data trustworthiness, not cosmetics.

## 1. The Loop (run for every objective)

Each step is a gate. Do not advance until the current step is satisfied.

| # | Step | What it means here |
|---|---|---|
| 1 | **Understand objective** | Restate the goal in one sentence. Who is it for (which persona)? Which priority does it serve? |
| 2 | **Analyze existing implementation** | Find the code that already does this or something near it. Reuse beats rebuild. Read the routers, services, models, and tests involved. |
| 3 | **Review architecture** | Where does this fit in `ARCHITECTURE.md`? Which axis/owner does it touch? Does it cross a tenant or source-of-truth boundary? |
| 4 | **Identify risks** | Run the SWAT review (§2). Name the safety, reliability, security, and data-integrity exposure *before* designing. |
| 5 | **Design solution** | Prefer additive, read-only, flag-gated. Write down the data flow and the rollback path. |
| 6 | **Compare alternatives** | List at least two approaches. State the trade-off against the priority order. |
| 7 | **Choose safest approach** | Highest item in the priority order wins. Smallest blast radius wins ties. |
| 8 | **Implement smallest safe change** | One concern per change. New behavior behind a `FEATURE_*` flag defaulting off. Never modify a migration that has shipped — add a new one. |
| 9 | **Verify correctness** | `cd api && python -m pytest -q` and `cd web && npm run build` must pass (this is exactly what CI enforces). Add/extend tests for the new path *and* the flag-off path. |
| 10 | **Review UX** | Calm, plain-language, honest. No false "all good". Empty states guide, not blank. Check the relevant persona. |
| 11 | **Review security** | Auth/tenant isolation intact? No secrets logged? Webhook auth unchanged or strengthened? New egress gated? |
| 12 | **Review performance** | New N+1 queries? Unbounded result sets? Added latency on a hot path (Command Center, health sync)? |
| 13 | **Review maintainability** | Does it read like the surrounding code? Is the flag documented in `config.py`? Will the next person understand *why*? |
| 14 | **Review technical debt** | Did this add debt? If so, log it in `BACKLOG.md` → Technical Debt. Did it let you retire debt? Do it. |
| 15 | **Update documentation** | The `docs/*` doc for the subsystem, plus inline `config.py` comments for any new flag. |
| 16 | **Update project state** | Edit `docs/PROJECT_STATE.md`: move items between Completed / In progress / Blockers; refresh Known Risks. |
| 17 | **Recommend next priorities** | End every session with the top 1–3 next actions, ranked by the priority order. |

## 2. SWAT Review Discipline

Run this aggressively at step 4 (before design) and again at step 13–14 (after
implementation). Answer each — "nothing" is a valid answer, but you must look.

- **What is wrong?** — incorrect logic, a false safety claim, a broken contract.
- **What is fragile?** — depends on env-var-per-service, undocumented order,
  network without timeout, a single point of failure.
- **What is confusing?** — would mislead the next engineer or a support tech.
- **What is duplicated?** — same logic in two places that will drift (e.g. status
  normalization, permission checks).
- **What is unnecessary?** — dead code, an unused flag, a surface no one reads.
- **What creates future technical debt?** — shortcuts, missing tests, a flag with
  no removal plan.
- **What creates customer frustration?** — noise, jargon, false alarms, slow pages.
- **What creates support burden?** — unexplained status, no reason codes, no
  runbook.
- **What creates legal / compliance / operational risk?** — E911 correctness,
  data retention, tenant leakage, a life-safety guarantee we can't back.
- **What can be simplified?** — fewer flags, fewer code paths, one source of truth.

## 3. Hard Stops (refuse or escalate)

Stop and get explicit human approval before:

- Modifying or deleting an Alembic migration that has already shipped.
- Any change that could **write** to `sites.status`, `devices.status`,
  `lines.status`, E911 fields, or Zoho lifecycle state outside the existing
  gated, dry-run-first planners.
- Flipping a `FEATURE_*` flag on in `render.yaml` (especially
  `LLLM_ALLOW_EXTERNAL`, `TMOBILE_PIT_LIVE_CALLS_ENABLED`, or any
  write-enabling flag).
- Sending any **live** carrier call (T-Mobile activation, Verizon write).
- Changing webhook authentication or CORS/JWT configuration.
- Anything that touches the demo seed path on the production start command.

## 4. Definition of Verified

"It works" is not a claim until you have run the tests and the build and reported
the actual result. If tests fail, say so with the output. If a step was skipped,
say which. Do not hedge a verified result and do not assert an unverified one.

## 5. Session Wrap

Before ending: tests + build green (or explicitly noted), `PROJECT_STATE.md`
updated, `BACKLOG.md` updated if debt/ideas surfaced, and a ranked
"next priorities" list delivered to the user.
