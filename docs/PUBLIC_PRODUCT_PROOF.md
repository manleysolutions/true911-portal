# Public Product Proof: controlled product imagery

> **Status: PROPOSED (Stuart's direction, 2026-10-02). Not implemented. Draft
> decision below, not yet recorded in `DECISIONS.md`.**
> **Authority Level:** 3 (Execution, planning). **Governed by:** `CONSTITUTION.md`;
> public claims follow D-030; the hero direction is O1 (`ACQUISITION.md` §10).
> Part of the public acquisition path:
> public website → **product proof** → Life-Safety Assessment → qualification →
> controlled demonstration → conversion/onboarding (`CUSTOMER_LIFECYCLE_PLAN.md` §I).

## 1. The problem

The public site has no visual proof that True911 is a substantial, modern operating
system. But True911's workflows, data model and operational intelligence are
competitive IP. The goal is therefore **controlled disclosure**:
- show that the product is real and mature;
- never provide a usable blueprint of how it works.

## 2. Rules (non-negotiable)

1. **Synthetic or demo data only.** Never production customer data. Never RH,
   Integrity Property Management or any other real tenant. That rules out, even
   blurred:
   - real names, addresses, phone numbers and contacts;
   - ICCID, IMSI, IMEI, SIM ids, serials, SIP or carrier-account information;
   - internal or device ids;
   - billing, E911 records, support requests or activity history.
2. **The asset itself must be safe.** Never ship a detailed image and hide parts of
   it with CSS blur, opacity, overlays, masks, gradients or JavaScript. The
   PNG/WebP/AVIF file must be safe if someone downloads it directly.
3. **Abstract, don't blur.** In the capture, replace sensitive regions with neutral
   placeholder shapes (skeleton bars, generic chips). Real-looking text that is
   blurred invites reconstruction and looks fake.
4. **The truth model still applies to synthetic data.**
   - No green "Verified" E911 (there is no provider verification for the customer view).
   - No fabricated service or connection totals.
   - UNKNOWN is never healthy.
   - No impossible combinations just because they look good.
   - Every public product image carries the caption **"Product UI · Sample data"**.
5. **Two reviews before publication:** a customer-data disclosure review and a
   competitive disclosure review (§6). Both are recorded in the PR.

## 3. Disclosure levels

| Level | Where | Purpose | Detail allowed |
|---|---|---|---|
| **1. Homepage** | `/` | "This is a real system managing an entire portfolio." | Branding, Command Center frame and navigation, generic map with synthetic markers, 2–3 high-level status cards. Detail rows abstracted. |
| **2. Product pages** | `/true911-platform` | One concept per image | Tight crops; partial UI; each crop shows one idea. |
| **3. Qualified demo** | Live, guided, controlled demo tenant | Full workflow | Everything, but **never downloadable public website material**. |

## 4. Placements on the current site

Current homepage order (`web/src/pages/public/LandingPage.jsx`): Hero → The
Problem → The Solution → Benefits → Connectivity → Who it's for → Regulatory
context → Final CTA.

- **Homepage, new "product proof" band directly under the hero CTAs** (direction O1).
  The large Command Center composition (image P1) fades into the page background.
  Copy (draft, within the D-030 vocabulary; no unsupported promise):
  > **One view across your life-safety communications**
  > See your locations in one place. Know what needs your attention. See what True911
  > is working on.
  > *Product UI · Sample data*

  "See every location" was avoided as a blanket claim: the product shows the
  locations True911 knows about.
- **Homepage, Benefits:** no images. The cards stay text, which keeps the page
  light. Optional later: P3 beside "Status across every location" and "Documented
  incident handling".
- **Platform page, "What the platform does":** pair P2 with *Portfolio visibility*,
  P3 with the ownership idea, P4 with *Location records*, and P5 with *Monitoring
  and alerts*. "How it works" stays text-only.
- **Never:** the Life-Safety Assessment or quote forms (keep them focused), and
  any page reachable without the "Sample data" caption.

## 5. Proposed images (from existing Command Center surfaces)

Source surfaces: `web/src/components/customer/`. That means CustomerShell, the
StatusStatement and tiles, CommandMap, the ActionCenter rail and tiers, the
Locations view, and the LocationCommandCenter dialog.

### P1: Command Center overview (homepage hero)
- **Sharp:**
  - the Beacon and "True911" wordmark;
  - the top navigation (Overview · Action Center · Locations);
  - the portfolio title "True911 Demo Portfolio";
  - a status statement in plain words (e.g. "2 locations need attention");
  - two tiles, *Locations* and *Needs attention*, with synthetic counts;
  - the map, with generic synthetic markers and the OSM attribution visible;
  - the panel title "What needs your attention".
- **Abstracted:**
  - Action Center row text (skeleton bars and owner chips only);
  - the location preview rows;
  - the E911 tile body and the services tile;
  - search, refresh and account controls;
  - all timestamps.
- **Omitted:** the location dialog, request forms, the E911 wizard and any counts
  that imply service or connection modeling.

### P2: Portfolio map (platform page, "Portfolio visibility")
- **Sharp:** the map, about 6 synthetic markers in generalized regions, and a marker
  legend with plain words (icon + word, never colour alone). OSM attribution.
- **Abstracted:** marker popups, location names beyond 1–2 synthetic examples, and
  any "missing coordinates" counts.
- **Omitted:** filters (they reveal the status and E911 dimensions).

### P3: Ownership: "Your action" vs "True911" (platform page)
- **Sharp:** the two owner chips, "Your action" and "True911", and 1–2 rows with
  generic titles ("Confirm contact details", "True911 is reviewing a location").
- **Abstracted:** the tier structure (no tier names or counts) and row metadata.
- **Omitted:** the full tier model (Urgent / Action needed / In progress / Portfolio
  setup / Recent activity) and any request lifecycle states.

### P4: Location record (platform page, "Location records")
- **Sharp:** a synthetic location name ("North Distribution Center"), the Location
  ID label, the four tab labels in neutral form, and one generic "Address on file"
  line.
- **Abstracted:** all tab bodies except a placeholder, the service and line list,
  contacts and activity.
- **Omitted:** the Services & Lines detail (it reveals service → connection →
  equipment modeling) and the E911 wizard steps.

### P5: E911 readiness concept (platform page; optional)
- **Rendered as an illustration, not a screenshot:** the three parts named in plain
  words: *Address on file · Your confirmation · Official verification*.
- **Omitted:** wizard steps, attestation text, review states and verification sources.

## 6. Competitive disclosure review (assessment of P1–P5 as specified)

| Question | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| Data model (location → service → connection → asset)? | No | No | No | No (service list omitted) | No |
| E911 workflow reconstructable? | No | No | No | No | Concept only (three public dimensions, already in copy) |
| Action Center decision model? | No (rows abstracted) | No | Partial: the existence of customer vs True911 ownership. This is a value proposition, accepted. | No | No |
| Health calculation? | No (no reason codes) | No | No | No | No |
| Reconciliation states, confidence or provenance? | No | No | No | No | No |
| Carrier or source integrations? | No | No | No | No | No |
| Sequential controls enough to reproduce a workflow? | No | No | No | No | No |

**Marketing-value review:**
- **P1** proves the product is real and portfolio-scale.
- **P2** shows visibility.
- **P3** carries the ownership message.
- **P4** shows depth per location.
- **P5** explains E911 truthfully.

If a reviewer can't tell what an image is for within about 5 seconds, it is too
obscured.

**Larger disclosure vectors found during this review (more significant than any screenshot):**
1. **The production API publishes its full schema.** `/docs`, `/redoc` and
   `/openapi.json` (≈548 KB) are publicly reachable on `true911-api.onrender.com`.
   They reveal every endpoint and model: canonical inventory, reconciliation,
   Action Center, E911 and customer self-service.
   **Recommendation (needs approval; it is a live change):** disable these in
   production (`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` when
   `APP_MODE=production`, or gate them behind internal auth).
2. **The portal JavaScript chunk is publicly downloadable**, though minified and
   without source maps (verified: no `sourceMappingURL`). Its UI logic and copy can
   be inspected. This is inherent to an SPA. Keep proprietary logic server-side,
   and don't embed internal terminology or decision tables in client code where
   avoidable.
3. **The existing demo seed (`api/app/seed.py`) is unsuitable for marketing.** It
   names real public agencies (e.g. "City of Dallas", "Houston PD") with real
   addresses, and uses legacy states (`Connected`, uptime %) that don't follow the
   truth model. PP-1 replaces it for marketing purposes.

## 7. Sanitization pipeline (repeatable)

```
PP-1 synthetic fixture (JSON, versioned, reviewed)        ── never production data
        ↓
PP-2 capture build: local / CI-only render of the real customer components fed by
     the fixture (no production API, no production DB, not a public route)
        ↓
capture (headless browser, fixed viewport, reduced motion)
        ↓
crop → abstract (replace detail regions with placeholders) → flatten (single raster layer)
        ↓
export WebP/AVIF (+ PNG fallback only where needed); strip all metadata (EXIF, XMP,
PNG text chunks, ICC except sRGB); neutral filenames (e.g. product-overview-1440.avif)
        ↓
review: customer-data + competitive disclosure (checklist in the PR)
        ↓
commit ONLY the final flattened assets to web/public/product/ ── never the raw capture,
layered sources, fixture-detail captures or design files
```

Guards to add in PP-3:
- a test that `web/public/product/` contains only approved filenames and formats;
- an automated metadata-free check;
- the "Sample data" caption present wherever an image is used;
- alt text that is generic, e.g. "True911 Command Center with sample data" with no
  record detail.

## 8. Synthetic demo portfolio (PP-1)

- **Display identity:** "True911 Demo Portfolio".
- **Locations:** Downtown Campus, Medical Center, North Distribution Center,
  Administration Building, Parking Garage, Operations Center.
- **Geography:** generalized and fictional. Markers sit at regional placeholder
  points, not real parcels. No real street addresses; use clearly fictional ones if
  any address appears ("100 Example Way").
- **Contents:** elevator, fire-alarm and emergency-phone services, plus a realistic
  mix that the truth model allows:
  - a location needing attention (known problem);
  - one True911 is reviewing ("being confirmed");
  - one being set up (planned, D-034);
  - healthy ones only where evidence-backed in the fixture;
  - customer action items;
  - E911 shown as address on file, or confirmation needed, never "Verified".
- **Phone numbers:** if any appear, only reserved fictional ranges (555-01xx).
- **Where it lives:** in the repo as a reviewed fixture, used by PP-2 captures and
  the PP-5 demo tenant. It is not loaded into the production database for
  marketing captures.

## 9. Draft decision (for Stuart's wording approval; NOT recorded)

> **Proposed D-040: Public product proof.** True911 may publicly display controlled
> product imagery to demonstrate product reality and operational value. Public
> product imagery:
> 1. uses synthetic/demo data only;
> 2. never originates from production customer screenshots;
> 3. intentionally limits disclosure of proprietary workflows and internal
>    architecture;
> 4. is flattened and redacted before entering the public web asset pipeline;
> 5. contains no recoverable hidden or blurred source information;
> 6. undergoes both customer-data disclosure review and competitive-disclosure
>    review.
>
> Full workflow demonstrations are reserved for controlled sales/demo environments.

## 10. Implementation slices (proposed; none started)

| Slice | Scope | Notes |
|---|---|---|
| **PP-0** (**in review: PR #203**) | Disable `/docs`, `/redoc`, `/openapi.json` (and `/docs/oauth2-redirect`) in production | Docs are served only when `APP_MODE` is exactly `demo`; production, missing or unknown values disable them. Exposure-audit findings (debug CORS route, malformed production `CORS_ORIGINS`, public feature flags) are in BACKLOG A15, not fixed by PP-0 |
| **PP-1** | Synthetic marketing fixture specification + fixture file | Truth-model tests over the fixture |
| **PP-2** | Capture build: render the customer components from the fixture, local/CI only | Not a production route; reuses the headless-Edge capture method |
| **PP-3** | Homepage product-proof band with P1 | Asset guards (§7); D-030 copy review; LCP/performance budget |
| **PP-4** | Platform-page crops P2–P5 | One concept per image |
| **PP-5** | Sales demo environment (isolated demo tenant / `true911-web-demo`) | Level 3; not public; demo access controlled |

Kept out of CT-1/CT-2 (#202) and any conversion-truth work.
