# T-Mobile Private Key — Security Remediation (BACKLOG C1)

> Status: **working-tree cleanup done in this branch; key rotation + Render update
> are MANUAL steps the operator must perform (see §5).**
> Opened: 2026-06-13. Owner: Manley Solutions / True911 platform.
> Related: `docs/tmobile_taap_setup.md`, `docs/BACKLOG.md` (C1), `docs/ARCHITECTURE.md` §11.

## 1. Incident

A 2048-bit RSA **private** key was committed to the repository as
`api/tmobile_private.pem` (PKCS#8, `-----BEGIN PRIVATE KEY-----`), alongside its
public key `api/tmobile_public.pem`.

- **Introduced in commit:** `a65d7a3` ("Add line intelligence engine scaffold…").
- **Footprint:** that commit is an **ancestor of `main`** and ~90 local and remote
  branches, and has been **pushed to `origin`** (`github.com/manleysolutions/true911-portal`).
- **Therefore the private key must be treated as compromised.** Anyone with repo
  access (current or historical clone) has the key. Removal from the working tree
  does **not** undo exposure — **rotation is mandatory and is the primary control.**

This key is the RSA signing key for T-Mobile Wholesale TAAP **Proof-of-Possession
(PoP)** tokens. With it, an attacker who also holds the consumer key/secret could
sign requests as us. The key's blast radius is the T-Mobile Wholesale integration
(currently PIT environment by default; live calls additionally hard-gated by
`TMOBILE_PIT_LIVE_CALLS_ENABLED`).

> **Needs Verification:** confirm whether the committed key was a throwaway PIT-only
> key or one ever registered for production. Either way, rotate it.

## 2. What this branch changed (no product behavior change)

1. **Removed** `api/tmobile_private.pem` and `api/tmobile_public.pem` from the
   working tree and git index (`git rm`). No application code loads these files —
   the public key is derived at runtime by
   `tmobile_taap.py::_derive_public_key_pem`, and the private key default path
   (`TMOBILE_PRIVATE_KEY_PATH`) is `""`, so nothing read the committed files.
2. **Added** `api/tmobile_private.pem.example` — a clearly non-functional
   placeholder documenting the local-dev and production patterns.
3. **Hardened `.gitignore`** (root + `api/`) to ignore `*.pem`, `*.key`, `*.crt`,
   `*.cert`, `*.p12`, `*.pfx`, ssh keys, and common secret files. Tracked
   `*.example` placeholders are deliberately *not* matched.
4. **Documented** the env-var loading pattern in `.env.example` and
   `docs/tmobile_taap_setup.md`.

**No code path changed.** Environment-variable loading already existed and is the
preferred path: `_load_private_key()` reads `TMOBILE_PRIVATE_KEY_PEM` first
(handling escaped `\n`), then falls back to `TMOBILE_PRIVATE_KEY_PATH`.

## 3. Required configuration (no key file in production)

| Variable | Use | Where |
|---|---|---|
| `TMOBILE_PRIVATE_KEY_PEM` | **Preferred.** Full PEM content; escaped `\n` is auto-converted. | Render secret (dashboard, `sync:false`) |
| `TMOBILE_PRIVATE_KEY_PATH` | Local dev only — path to a self-generated, git-ignored key. | `api/.env` |

Production must set `TMOBILE_PRIVATE_KEY_PEM` and leave `TMOBILE_PRIVATE_KEY_PATH`
empty. The loader prefers the PEM env var, so even if both are set the env var wins.

## 4. Git history cleanup — decision & options

**Decision: rotation is the required fix. History rewrite is OPTIONAL and lower
priority, and must NOT be performed without explicit approval** (Operating Loop
§3 Hard Stop — history rewrite is destructive and coordination-heavy).

Rationale: the commit is an ancestor of `main` and ~90 branches already on
`origin`. The leaked key already exists in every clone and on GitHub. Once the key
is **rotated** (§5), the copy in history is **dead** — rewriting history then only
removes a worthless artifact, at high cost.

If, after rotation, you still want the key purged from history (e.g. policy,
audit), the recommended approach:

### Option A — `git filter-repo` (recommended over filter-branch / BFG)
```bash
# 0. PRE-REQ: key already rotated; schedule a maintenance window; notify all
#    collaborators (they must re-clone afterward). Close/rebase open PRs.
pip install git-filter-repo

# 1. Fresh mirror clone
git clone --mirror https://github.com/manleysolutions/true911-portal.git
cd true911-portal.git

# 2. Strip the files from ALL history
git filter-repo --path api/tmobile_private.pem --path api/tmobile_public.pem --invert-paths

# 3. Force-push the rewritten history (rewrites main + all branches + tags)
git push --force --all
git push --force --tags
```
**Consequences:** every commit SHA after the introduction point changes; all open
PRs break; everyone must re-clone (a normal `pull` will fail/duplicate); Render
deploy history references old SHAs. This is why it is gated behind explicit approval.

### Option B — accept history, rely on rotation (default recommendation)
Rotate the key (making the leaked one useless), document the incident (this file),
and do **not** rewrite history. Lowest operational risk. Most appropriate when the
key was PIT-only and is promptly rotated.

> GitHub also caches commits via the API for some time; even after a rewrite,
> contact GitHub Support to purge cached views if required by policy.

## 5. MANUAL steps for the operator (outside Claude)

These cannot and should not be done by the assistant — they involve live secrets
and a third-party portal.

1. **Generate a new key pair** (local, on a trusted machine):
   ```bash
   openssl genrsa -out tmobile_private_new.pem 2048
   openssl rsa -in tmobile_private_new.pem -pubout -out tmobile_public_new.pem
   ```
   (These filenames are git-ignored; do not add them to the repo.)
2. **Register the new public key with T-Mobile** — send `tmobile_public_new.pem`
   to your Wholesale account manager and request that the **old** public key be
   **deregistered/revoked**.
3. **Update Render** — in the `true911-api` (and any other service that signs
   T-Mobile requests, e.g. `true911-worker` if applicable) set
   `TMOBILE_PRIVATE_KEY_PEM` to the new key's PEM content. Ensure
   `TMOBILE_PRIVATE_KEY_PATH` is unset/empty in production.
   > Check flag/secret parity across services (project memory: PR #63 env-var-per-service pitfall).
4. **Verify** with the non-sending dry run (no live call, no secret printed):
   ```bash
   cd api && python ../scripts/test_tmobile_taap.py --dry-run
   ```
   Confirm key loads and PoP token structure is valid. Do **not** run live
   activation (`TMOBILE_PIT_LIVE_CALLS_ENABLED` stays `false` unless separately
   approved).
5. **Confirm old key is dead** — once T-Mobile deregisters the old public key, any
   request signed with the leaked private key will fail PoP validation.
6. **(Optional, approval-gated)** perform the history rewrite per §4 Option A.
7. **Securely delete** local copies of the old private key.

## 6. Verification done in this branch

- `git rm` confirmed: only `api/tmobile_private.pem.example` remains in `api/*.pem*`.
- Backend tests run (see PR description). The T-Mobile TAAP tests generate their own
  keys in `tmp_path` and do not depend on the removed files.
- `.gitignore` updated so a regenerated `tmobile_private.pem` cannot be re-added.
