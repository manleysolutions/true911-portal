# RH Life-Safety Service Certification Gap — 2026-10-02

> **FRESH PRODUCTION TRUE911 DRY-RUN + READ-ONLY ZOHO/NAPCO SOURCE RECONCILIATION.**
> **This is analysis only.** No canonical data is production-applied (no `--apply`).
> No source record was changed. No operator decision was recorded. E911 is
> untouched, and no customer was invited.
>
> **Inputs:**
> - `canonical_service_backfill` dry-run, generated_at `2026-10-02T15:38:18Z`
>   (sources ok; operator_decisions active=0);
> - read-only query: 45 PortfolioBuildings, all `approved=True, status=active`;
> - the Zoho/NAPCO evidence reconciliation of 2026-10-02 (Zoho Subscription_Mgmnt
>   101 RH records; NAPCO radiolist 2026-09-30).
>
> **Labels:** SOURCE FACT · CANONICAL INFERENCE · SOURCE DATA ERROR · IDENTITY
> CONFLICT · OPERATOR DECISION REQUIRED · INSUFFICIENT EVIDENCE.
>
> SIM/IMEI values are omitted. **No grand total is stated:** the engine itself
> reports "no single precise total".

> ⛔ **THE 2026-10-02 15:38Z DRY-RUN MUST NOT BE USED AS AN APPLY MANIFEST.**
> It exposed canonical-engine defects:
> 1. device serials became NAPCO radio keys;
> 2. one radio became two services;
> 3. `napco:` was asserted without NAPCO evidence;
> 4. SKU and telephone-line records were taken as FACP evidence;
> 5. Zoho "Activated" alone made services CURRENT and counted, although an
>    administrative status is not deployment proof.
>
> These are fixed in `fix/canonical-radio-identity` (PR #205; see
> `CANONICAL_SERVICE_MODEL.md` §5a–§5b). The run is preserved unchanged as audit
> evidence. Its service keys (`FACP:napco:…`, `FACP:zoho:…`) and the counts in
> §1–§4 describe the defective engine. The matrix must be rebuilt from a fresh
> read-only dry-run after that fix is merged and deployed. **No new import is
> needed:** the engine reads the already-stored 2026-09-30 NAPCO snapshot as-is.

## 1. Engine baseline (fresh)

| | Value |
|---|---|
| Buildings | 45 |
| Confirmed counted services | 26 (FACP 9, ELEVATOR 17, EMERGENCY_PHONE 0) |
| Required confirmed connections | 35 |
| Probable services | 13 (+17 probable connections) |
| Unresolved services | 9 |
| Unclassified "current" lines | 13 |
| Unplaced numbers | 3 |
| Historical assets | 41 |

## 2. Findings that change the reading of the engine output

1. **CANONICAL INFERENCE ERROR: telephone-device serials are read as NAPCO FACP identities.**
   - **Houston `napco:202301010000027`:** CONFIRMED/CURRENT/**COUNTED** as FACP. It is
     the serial of the MS130v4 telephone device on Zoho #4961 (`7134464506`), which was
     created as Elevator and relabelled Alarm Panel (SOURCE FACT).
   - **Jacksonville `napco:202104030000068`** (UNRESOLVED FACP) is the serial of the
     old device on Zoho #914 (SOURCE FACT).
   - **The same 13–15-digit serial pattern appears on 5 more UNRESOLVED "FACP"
     findings** (Chicago, Memphis, NYC Flagship, Long Beach, San Francisco Pier 70,
     Toronto). That these are serials is an INFERENCE.
   - **Effect:** Houston's counted FACP (2 connections) is not certifiable, and most
     "unresolved FACP" items are not FACPs.
2. **CANONICAL INFERENCE ERROR: Zoho FACP records are not merged with their own radio.**
   - Princeton Zoho #578 (`…41963028`) carries Starlink `11187020`, the same radio as
     `napco:11187020`. Its sibling `…69320004` is a dropped-digit duplicate (`1187020`).
   - Houston Zoho #264991 (`…66251001`) carries `1554387`, the same as `napco:1554387`.
   - **Effect:** 4 of the 13 PROBABLE services are double representations, not
     additional services.
3. **INSUFFICIENT EVIDENCE: an engine "napco:" key need not exist in NAPCO.**
   Roseville `napco:1015523` is COUNTED, but `1015523` is absent from the NAPCO export.
   It was hand-created in Zoho, is flagged for review, and was never validated.
   Houston `1554387` and Boston `1380014` are also absent.
4. **IDENTITY CONFLICT in True911's registry (not only in Zoho).**
   - **Approved "Beverly Modern Gallery"** carries store 150 / "8772 Beverly Blvd,
     Leawood". It holds Leawood's elevator (`9132639240`, Zoho "150 Leawood"),
     Leawood's two radios (`14046892`, `14051540`) and Beverly Modern #351's radio
     (`10107087`). Zoho shows these are two facilities (stores 150 and 351), and there
     is no separate approved Leawood building.
   - **Approved "Hollywood Gallery"** (store 0) carries Melrose #146's address and
     radio (`10721045`), plus the de-activated Hollywood placeholder line.
   - **Approved San Rafael building** is the suspended 9000 Northgate address, while the
     current radio `9872590` is at 20 Front Street.
   - **Two approved buildings for store 405** ("#405 Southgate Centre", with no
     evidence, and "Edmonton, AB – Store 405 Southgate Centre").
5. **The HIGH `ASSET_PLACEMENT_CONFLICT` `***8E14` is on a DECOMMISSIONED device.**
   Dallas #168 and Oakbrook #176 have only historical evidence, so the conflict affects
   lineage, not any current certification.
6. **Lifecycle:** 3 of the 13 "unclassified current" lines have lifecycle UNKNOWN
   (Austin `4104994050`, Greenwich `5106814382`, SF `4157186180`).

## 3. 45-location matrix

**Columns:**
- **Conf.** = engine CONFIRMED + CURRENT + COUNTED, with corrections noted;
- **Floor** = required connections of those services;
- **Prob** / **Unres** = probable / unresolved services;
- **Uncl** = unclassified lines;
- **Hist** = historical assets;
- **ID?** = identity conflict;
- **Src?** = source-data issue;
- **Vis** = customer-safe certified service visible after CG-1 + apply + #186b.

| # | Building | Store | Class | Conf. | Floor | Prob | Unres | Uncl | Hist | ID? | Src? | Primary blocker | Required action | Vis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Austin Gallery | 149 | B | ELEV 1 | 1 | 0 | 0 | 1 (UNKNOWN) | 0 | No | No | line 4104994050 unclassified, lifecycle unknown | classify the line | Yes (ELEV) |
| 2 | Beverly Modern Gallery | 150 (wrong) | **D** | ELEV 1, FACP 1 (engine) | 3 | 0 | 0 | 0 | 0 | **Yes** | Yes | building conflates Leawood #150 and Beverly Modern #351 | registry identity correction (separate Leawood; Beverly Modern = 351) | No |
| 3 | Chicago Gallery | 147 | C | 0 | 0 | 1 ELEV | 1 (serial-pattern "FACP") | 1 | 0 | No | No | no confirmed service | confirm elevator 3127149990; classify 3127148045 | No |
| 4 | Dallas Gallery | 168 | E | 0 | 0 | 0 | 0 | 0 (3 decommissioned) | 7 | historical only | — | no current evidence | resolve `***8E14` lineage (history only) | No |
| 5 | Hollywood Gallery | 0 | **D** | 0 (2 FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 (1 decommissioned) | 3 | **Yes** | Yes | building is Melrose #146 under a store-0 placeholder | registry identity correction | No |
| 6 | LaSalle Gallery | — | E | 0 | 0 | 0 | 0 | 0 | 1 | No | — | historical only | none for certification | No |
| 7 | Linden House Gallery | — | B | ELEV 1 | 1 | 0 | 0 | 1 | 0 | No | No | 3173312088 unclassified | classify the line | Yes (ELEV) |
| 8 | MDC Distribution Center | — | **A** | FACP 1 | 2 | 0 | 0 | 0 | 0 | No | No (its ID was cloned into Houston #4978; MDC's own record unaffected) | — | confirm radio in NAPCO export | Yes (FACP) |
| 9 | Memphis Gallery | — | **D** | 0 (2 FACP lifecycle UNKNOWN) | 0 | 1 ELEV | 1 (serial-pattern) | 1 | 0 | **Yes** | Yes | all older RH Zoho records were under "RH MEMPHIS" until re-pointed in 2025–26; evidence ownership doubtful | BUILDING_IDENTITY_SUSPECT review | No |
| 10 | Patterson Warehouse | — | **A** | FACP 1 | 2 | 0 | 0 | 0 | 0 | No | No | — | confirm radio in NAPCO export | Yes (FACP) |
| 11 | Pembroke Gallery | — | E | 0 | 0 | 0 | 0 | 0 (1 suspended) | 3 | No | — | suspended / historical only | none | No |
| 12 | Pleasanton Gallery | — | B | ELEV 1 | 1 | 0 | 1 FACP (15024451) | 0 | 0 | No | No | radio 15024451 unresolved | NAPCO / site evidence for the radio | Yes (ELEV) |
| 13 | Princeton Gallery | 644 | C | 0 (2 FACP lifecycle UNKNOWN) | 0 | 2 FACP (both duplicates) | 0 | 0 | 0 | No | Yes | #903 (5456099) unresolved; 11187020 lifecycle unknown | merge #578 with 11187020; classify #903 | No |
| 14 | RH NYC Flagship | — | B | ELEV 1 | 1 | 1 ELEV | 1 (serial-pattern) | 0 | 0 | No | No | probable elevator; 2 FACP lifecycle UNKNOWN | confirm 3475993067; FACP lifecycle | Yes (ELEV) |
| 15 | Short Hills | 048 | E | 0 | 0 | 0 | 0 | 0 (1 decommissioned) | 3 | No | — | historical only | none | No |
| 16 | Charlotte | 174 | C | 0 | 0 | 0 | 0 | 1 | 0 | No | No | only an unclassified line | classify 7049065192 | No |
| 17 | Oakbrook | 176 | E | 0 | 0 | 0 | 0 | 0 (2 decommissioned) | 5 | historical only | — | no current evidence | `***8E14` lineage (history only) | No |
| 18 | Cleveland | 187 | **A** | ELEV 1 | 1 | 0 | 0 | 0 | 0 | No | No | — | — | Yes (ELEV) |
| 19 | #405 Southgate Centre | 405 | **D** | 0 | 0 | 0 | 0 | 0 | 0 | **Yes** | Yes | duplicate approved building of #27 | registry merge decision | No |
| 20 | Katy Mills | 645 | E | 0 | 0 | 0 | 0 | 0 | 2 | No | — | historical only | none | No |
| 21 | Irvine | 646 | E | 0 | 0 | 0 | 0 | 0 | 0 | No | — | no evidence | none | No |
| 22 | Boca Raton | 654 | C | 0 | 0 | 0 | 0 | 1 (+1 suspended) | 2 | No | No | only an unclassified line | classify 5613768862 | No |
| 23 | Atlanta | 145 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence for 11231222 | No |
| 24 | Bloomfield Hills | 652 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence for 11266477 | No |
| 25 | Clearwater | 657 | E | 0 | 0 | 0 | 0 | 0 | 0 | No | — | no evidence | none | No |
| 26 | Dawsonville | 604 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No (duplicate legacy site = cleanup) | No | 9742697 lifecycle unknown (Zoho Activated; NAPCO last signal 2024-02-09) | lifecycle decision from NAPCO/Zoho evidence | No |
| 27 | Edmonton | 405 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | Yes (duplicate #19) | FACP lifecycle unknown | lifecycle evidence for 9349094 | No |
| 28 | Gilbert | 642 | C | 0 (2 FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence | No |
| 29 | Greenwich | 144 | B | ELEV 1, FACP 2 | 5 | 0 | 0 | 1 (UNKNOWN) | 0 | No | No | 5106814382 unclassified, lifecycle unknown | classify the line | Yes (ELEV, 2 FACP) |
| 30 | Houston | 140 | B | ELEV 2 (engine also counts a spurious FACP) | 2 (engine 4) | 2 FACP (one is a Boston record; one duplicates 1554387) | 0 | 0 | 0 | partial (Boston record placed here) | Yes | spurious FACP; Boston record; 1554387 not in NAPCO; 7134464506 role | reject serial-FACP; unplace `…64115039`; classify 7134464506 | Hold (see §6) |
| 31 | Jacksonville | 177 | B | ELEV 2 | 2 | 6 ELEV (old lines) | 1 (old device serial, not an FACP) | 5 (+1 suspended) | 2 | No | Yes | old six, 5 Voice lines, duplicate 9046490389 | see §5 | Yes (2 ELEV) |
| 32 | Long Beach | 613 | B | ELEV 1 | 1 | 0 | 1 (serial-pattern) | 0 | 0 | No (duplicate = cleanup) | Yes (Zoho duplicate) | unresolved "FACP" is likely a device serial | serial fix ⇒ likely A | Yes (ELEV) |
| 33 | NYC Guesthouse | — | C | 0 (4 FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence | No |
| 34 | Portland | 155 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence | No |
| 35 | Roseville | 123 | C | 0 (engine counts FACP 1015523) | 0 (engine 2) | 0 | 0 | 0 | 0 | No (duplicate legacy site = cleanup) | Yes | 1015523 not in NAPCO; hand-entered | NAPCO / site evidence | No |
| 36 | San Francisco Pier 70 | 161 | B | ELEV 1 | 1 | 0 | 1 (serial-pattern) | 1 (UNKNOWN) + 2 decommissioned | 6 | No | No | 4157186180 unclassified; unresolved serial | classify the line; serial fix | Yes (ELEV) |
| 37 | San Rafael | 656 | **D** | 0 (2 FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 2 | **Yes** | Yes | approved building = suspended Northgate; current radio at 20 Front St | decide move vs two facilities; registry address | No |
| 38 | Toronto | 506 | B | ELEV 2, FACP 1 | 4 | 0 | 1 (serial-pattern) | 0 | 0 | No | No | unresolved serial "FACP" | serial fix ⇒ likely A | Yes (2 ELEV, FACP) |
| 39 | Tracy | 001 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | possible (store 001) | FACP lifecycle unknown | lifecycle evidence; confirm store number | No |
| 40 | Tulsa | 117 | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence | No |
| 41 | West Palm Beach | 160 | **A** | ELEV 2 | 2 | 0 | 0 | 0 | 0 | No | No | — | — | Yes (2 ELEV) |
| 42 | Cherry Hill | 640 | E | 0 | 0 | 0 | 0 | 0 | 1 | No | — | historical only | none | No |
| 43 | Richmond Gallery | — | C | 0 (FACP lifecycle UNKNOWN) | 0 | 0 | 0 | 0 | 0 | No | No | FACP lifecycle unknown | lifecycle evidence | No |
| 44 | Soda Grocery Gallery | — | **A** | FACP 1 | 2 | 0 | 0 | 0 | 0 | No | No | — | confirm radio in NAPCO export | Yes (FACP) |
| 45 | Vero Beach | 632 | C | 0 | 0 | 0 | 1 FACP (10719648) | 0 | 0 | No | No | radio unresolved | NAPCO / site evidence | No |

**Totals: A 5 + B 10 + C 16 + D 5 + E 9 = 45.**

- **A (5):** MDC, Patterson, Cleveland, West Palm Beach, Soda Grocery.
- **B (10):** Austin, Linden House, Pleasanton, NYC Flagship, Greenwich, Houston,
  Jacksonville, Long Beach, SF Pier 70, Toronto.
- **C (16):** Chicago, Princeton, Charlotte, Boca Raton, Atlanta, Bloomfield Hills,
  Dawsonville, Edmonton, Gilbert, NYC Guesthouse, Portland, Roseville, Tracy, Tulsa,
  Richmond, Vero Beach.
- **D (5):** Beverly Modern Gallery, Hollywood Gallery, Memphis, #405 Southgate Centre,
  San Rafael.
- **E (9):** Dallas, LaSalle, Pembroke, Short Hills, Oakbrook, Katy Mills, Irvine,
  Clearwater, Cherry Hill.

**Differences from the preliminary A5 / B9 / C15 / D8 / E8:**

| Building | Preliminary (inferred) | This analysis | Reason |
|---|---|---|---|
| Dallas, Oakbrook | D | **E** | The `***8E14` conflict is on a DECOMMISSIONED device; neither building has current evidence. |
| Long Beach | D | **B** | One building and one line; the duplicate legacy site and Zoho duplicate are cleanup only. It is B, not A, only because of the unresolved serial-pattern "FACP". |
| Dawsonville | D | **C** | Clear identity; the duplicate site is cleanup. Its only FACP has lifecycle UNKNOWN. |
| Roseville | D | **C** | Clear identity; the duplicate site is cleanup. Its counted FACP is absent from NAPCO. |
| Memphis | C | **D** | Zoho account lineage puts all older RH records under "RH MEMPHIS", so its evidence ownership is doubtful. |
| #405 Southgate Centre | E | **D** | A duplicate approved building for store 405. |

The preliminary per-building list was not supplied, so its column is inferred from the
counts.

## 4. Service summary

**ENGINE COUNTED (fresh dry-run):**
- Elevator 17, FACP 9, Emergency phone 0, other 0;
- 26 services and 35 required connections.

**CORRECTIONS to the engine count** (not certifiable as counted):
- Houston serial-FACP (−1 FACP, −2 connections);
- Beverly Modern Gallery (−1 ELEV, −1 FACP: building identity);
- Roseville FACP (−1: not in NAPCO).

**CERTIFIABLE AFTER CG-1 + apply + #186b (first slice, §7):**
- 20 services: 14 Elevator, 6 FACP;
- at 14 buildings.

**POTENTIALLY CERTIFIABLE AFTER OPERATOR REVIEW** (kept separate from the above):
- 27 confirmed FACPs with lifecycle UNKNOWN;
- probable elevators (Chicago, Memphis, NYC Flagship);
- 2 unresolved 8-digit radios (Pleasanton, Vero Beach);
- Princeton #903;
- Leawood's two radios;
- Jacksonville's 6 old lines, expected to be **historical**, not added.

**Not counted:**
- 13 unclassified lines (10 CURRENT, 3 lifecycle UNKNOWN);
- 3 unplaced numbers;
- 41 historical, suspended or decommissioned assets.

## 5. Jacksonville (Store 177)

- **CONFIRMED CURRENT:** elevators `9046890616`, `9046890656` (1 required connection
  each).
- **LIKELY HISTORICAL** (engine: PROBABLE CURRENT ELEVATOR; Zoho: Activated with no
  deactivation evidence): `9045829697`, `9045829756`, `9046249429`, `9046490309`,
  `9046490389`, `9046490394`. Zoho never labels any of them "elevator", so the engine's
  elevator classification of the old lines has no Zoho basis.
- **SUSPENDED / HISTORICAL:** `9046242986` ("Deactivated in TMO").
- **DUPLICATE SOURCE RECORD:** `9046490389` appears on two Zoho records with identical
  identifiers.
- **CURRENT UNCLASSIFIED:** `9046890633`, `9046891550`, `9046892688`, `9046892768`,
  `9047891030`. They have no purpose data.
- **"UNRESOLVED FACP" `202104030000068`:** not an FACP. It is the serial of the old
  device (Zoho #914).
- **EVIDENCE STILL NEEDED:**
  - Red Pocket / AT&T disconnect evidence before the old six become historical;
  - site evidence for the five Voice lines;
  - whether Jacksonville has an FACP at all, since no NAPCO radio is attributed here.

## 6. Operator punch list (nothing executed)

**Key to the three flags:**
- **Apply?** = blocks the first canonical apply;
- **Bldg?** = blocks that building's certification;
- **Wait?** = can wait until after Judy's launch.

| Group | Building | Evidence | Decision | Safest disposition | Apply? | Bldg? | Wait? |
|---|---|---|---|---|---|---|---|
| 1 Identity | Beverly Modern Gallery | store 150 / Leawood city; holds Leawood ELEV + 2 radios + Beverly Modern radio 10107087 | split the registry: Leawood #150 vs Beverly Modern #351 | mark BUILDING_IDENTITY_SUSPECT until split (nothing counted) | **Yes** | Yes | No for Leawood/Beverly certification, Yes for launch |
| 1 Identity | Hollywood Gallery | store 0; Melrose #146 address + radio 10721045; placeholder line | rename / re-identify as Melrose #146 (or split) | keep uncounted (already) | No | Yes | Yes |
| 1 Identity | San Rafael 656 | approved address = suspended Northgate; current radio 9872590 at 20 Front St | move vs two facilities | registry address to 20 Front St only if a move is confirmed | No (nothing counted) | Yes | Yes |
| 1 Identity | Memphis | contaminated account lineage | BUILDING_IDENTITY_SUSPECT? | suspect (strict reconcile) | No (nothing counted) | Yes | Yes |
| 1 Identity | #405 Southgate vs Edmonton 405 | two approved buildings, one store | merge or retire the empty one | registry decision | No | Yes (for #405) | Yes |
| 1 Identity | Houston | Zoho `…64115039` is Boston-account, ID not in NAPCO | placement | unplace from Houston | **Yes** | Yes | No |
| 1 Identity | Dallas #168 / Oakbrook #176 | `***8E14` decommissioned IMEI | lineage only | leave unresolved (history) | No | No | Yes |
| 2 FACP lifecycle UNKNOWN | Atlanta 11231222; Bloomfield 11266477; Dawsonville 9742697; Edmonton 9349094; Gilbert 9733541, 9743676; Houston 1554387; NYC Guesthouse 9872141, 9872196, 9881185, 9884458; Portland 11253529; San Rafael 9741483, 9872590; Tracy 12576269; Tulsa 12672873; Richmond 11191047; Princeton 11187020, 5456099; NYC Flagship 5484315, 5496688; Memphis 5492819, 5493999; Hollywood 10721045, 716051; Beverly Modern 14046892, 14051540 | confirmed radio, no lifecycle source | current vs historical | from source snapshots / NAPCO (#188), not recollection | No | Yes | Yes |
| 3 Probable FACP | Princeton `…41963028`, `…69320004`; Houston `…66251001`, `…64115039` | Zoho records without a NAPCO key | merge with their radio / reject duplicates | merge (engine), Zoho duplicate retire | No | No | Yes |
| 3 Serial-as-FACP | Houston 202301010000027 (**counted**); Jacksonville 202104030000068; Chicago 202207029000004; Memphis 202201011000009; NYC Flagship 202204025170011; Long Beach 2030101000034; SF 202305050000018; Toronto 202305050000006 | device serial pattern | not an FACP | engine fix (or reject the counted Houston one) | **Yes (Houston)** | Houston yes; others no | No (Houston) |
| 4 Unclassified lines | Austin 4104994050 (UNKNOWN); Chicago 3127148045; Linden House 3173312088; Memphis 6145899459; Charlotte 7049065192; Boca Raton 5613768862; Greenwich 5106814382 (UNKNOWN); Jacksonville 9046890633, 9046891550, 9046892688, 9046892768, 9047891030; SF Pier 70 4157186180 (UNKNOWN) | no source labels them | classify | leave UNCLASSIFIED until site evidence | No | B-to-A only | Yes |
| 5 Unplaced | `6462359804` | no key matched; not in the Zoho evidence file | placement | leave unplaced | No | No | Yes |
| 5 Unplaced | `9193495183` | Zoho: Raleigh #913 elevator, de-activated 2025-01-22 | none for the 45 | historical | No | No | Yes |
| 5 Unplaced | `9524860240` | Zoho: Edina #953 "Restoration Main Account", tags Deactivated / Zero Usage | none for the 45 | likely billing placeholder | No | No | Yes |
| 6 Duplicate legacy sites | Roseville SITE-1776961722516; Dawsonville SITE-1776962245029; Long Beach SITE-1776962277797 | an empty duplicate site at the building address | retire / ignore duplicate | cleanup; devices already placed via the asset id | No | No | Yes |
| 7 Unapproved candidates | Edina #159 | Activated radio 5483291; NAPCO names it "RALEIGH"; no signal since 2019 | registry approval + identity | keep outside the 45 | No | — | Yes |
| 7 Unapproved candidates | Raleigh #178 | Activated radio 5471872; de-activated elevator; two legacy sites | registry approval | keep outside the 45 | No | — | Yes |

## 7. First canonical apply gate (not approved)

`--apply` writes the whole projection to internal tables only; nothing
customer-facing reads them until #186b.

**MUST RESOLVE BEFORE THE FIRST RH APPLY** (so that nothing persisted as COUNTED is
wrong):
1. **Houston serial-FACP:** fix the engine so an MS130 serial is never a NAPCO FACP
   key, or record a SERVICE_APPROVAL=REJECTED decision for it. **Engine fix
   implemented** (`fix/canonical-radio-identity`, not yet merged): serials, IMEIs and
   ICCIDs can no longer become radio ids.
2. **Beverly Modern Gallery:** BUILDING_IDENTITY_SUSPECT (or a registry split) so the
   mixed Leawood / Beverly Modern evidence is not persisted as one building's counted
   services.
3. **Houston `…64115039`:** not placed to Houston.
4. **Counted FACPs without NAPCO corroboration (Roseville 1015523):** either feed the
   NAPCO export (source snapshots, #188) into confirmation, or do not count it. **The
   engine side is implemented** (`fix/canonical-radio-identity`): the engine now reads
   the latest NAPCO radiolist snapshot; a radio absent from it is capped at PROBABLE,
   with its lifecycle unchanged; a Zoho-only radio is PROBABLE. It reads the
   **already-stored** 2026-09-30 RH NAPCO snapshot as-is; no new import is needed.
   A service counts only with independent deployment evidence (e.g. a recent NAPCO
   signal), never on Zoho "Activated" alone.

**CAN REMAIN OPEN FOR THE FIRST INCREMENTAL APPLY** (they stay uncounted):
- lifecycle-UNKNOWN FACPs and probable or duplicate Zoho FACP records;
- the unresolved serial-pattern items (non-counted);
- unclassified lines and the Jacksonville old six;
- San Rafael, Hollywood, Memphis and #405 identity (nothing counted there);
- unplaced numbers, duplicate legacy sites, Edina / Raleigh, all Zoho corrections,
  and the historical `***8E14` lineage.

## 8. First customer certification slice (after CG-1 + approved apply + #186b)

20 services at 14 locations (CONFIRMED + CURRENT + cleanly placed). Each counted FACP
is gated on presence in the NAPCO export (Roseville's absence shows the need).

| Building | Services |
|---|---|
| MDC Distribution Center | FACP 15473583 |
| Patterson Warehouse | FACP 15472201 |
| Soda Grocery Gallery | FACP 15474214 |
| Cleveland #187 | ELEV 2163768632 |
| West Palm Beach 160 | ELEV 5612259100, 5612294240 |
| Austin #149 | ELEV 7373099667 |
| Linden House | ELEV 3172139000 |
| Pleasanton | ELEV 8284235102 |
| RH NYC Flagship | ELEV 6462350638 |
| Greenwich 144 | ELEV 2034963024, FACP 12885992, 15474067 |
| Jacksonville 177 | ELEV 9046890616, 9046890656 |
| Long Beach 613 | ELEV 5626151180 |
| SF Pier 70 161 | ELEV 4157183673 |
| Toronto 506 | ELEV 4254693082, 4255009452, FACP 9673016 |

- **Houston is held,** although its elevators are confirmed. Its records include a
  cloned device and a Boston record, so its placement needs a clean confirmation first.
- **Card:** "Known life-safety services · Certified at 14 of 45 locations · 31 locations
  still being finalized by True911", with per-location states Certified / Partially
  certified / Being finalized / No life-safety services on record.
- **Category counts are shown only as "at certified locations".**
- **Connection totals stay hidden.** Required paths are not certified individual
  connections.

## 9. Not changed by this analysis

Nothing applied; no operator decisions; no Zoho, NAPCO, registry, E911 or customer
changes; Judy not invited.
