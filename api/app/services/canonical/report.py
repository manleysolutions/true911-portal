"""Plain-text operator report for a canonical projection (INTERNAL ONLY).

SIM / IMEI / radio identifiers are masked.  Totals printed here are internal
reconciliation figures - they are NOT customer-facing in PR #186a.
"""

from __future__ import annotations

from app.services.canonical import vocab as V
from app.services.canonical.normalize import mask, naddr, words


def _line(*parts) -> str:
    return " | ".join("" if p is None else str(p) for p in parts)


def watchlist(snap: dict, res: dict, targets) -> list[str]:
    """Evidence for named review targets.  Suggests; never approves anything."""
    out = []
    names = res["building_names"]
    bids_by_site = {}
    for r in res["records"]:
        if r["source"] == V.SRC_TRUE911 and r["placement"]["building_id"] is not None:
            bids_by_site.setdefault(r["device"].get("site_id"), set()).add(
                r["placement"]["building_id"])
    linked_sites = set(bids_by_site)

    def mentions(text, toks):
        t = words(text)
        return any(" %s" % tk in t for tk in toks)

    for label, toks, store in targets:
        out.append("")
        out.append("## %s" % label)
        bl = [b for b in snap["buildings"] if mentions("%s %s" % (b["name"], b.get("city")), toks)
              or (store and str(b.get("store_number") or "").lstrip("0") == store)]
        for b in bl:
            out.append(_line("approved building", b["name"], "store=%s" % b.get("store_number"),
                             "addr=%s, %s" % (b.get("address"), b.get("city"))))
        ss = [s for s in snap["sites"] if mentions("%s %s %s" % (
            s.get("site_name"), s.get("street"), s.get("city")), toks)]
        for s in ss:
            out.append(_line("site", s["site_id"], s.get("site_name"), s.get("status"),
                             "%s, %s" % (s.get("street"), s.get("city")),
                             "devices placed to: %s" % (",".join(
                                 sorted(str(names.get(x)) for x in bids_by_site.get(s["site_id"], ())))
                                 or "none")))
        zz = [z for z in snap["zoho_rows"] if mentions("%s %s" % (z.get("facility"), z.get("account")), toks)]
        for z in zz:
            rec = next((r for r in res["records"] if r["rid"] == "zoho:%s" % z.get("zoho_id")), None)
            p = rec["placement"] if rec else {}
            out.append(_line("zoho", z.get("zoho_id"), z.get("facility") or z.get("account"),
                             z.get("connection_type"), z.get("activation"),
                             "placed=%s (%s/%s)" % (names.get(p.get("building_id")) or "UNPLACED",
                                                    p.get("confidence"), p.get("basis"))))
        if len(bl) > 1:
            verdict = "several approved buildings match - duplicate identity?"
        elif bl and any(s["site_id"] not in linked_sites for s in ss):
            addr = naddr(bl[0].get("address"), bl[0].get("city"), bl[0].get("state"))
            dup = [s["site_id"] for s in ss if s["site_id"] not in linked_sites
                   and naddr(s.get("street"), s.get("city"), s.get("state")) == addr]
            verdict = ("duplicate legacy site(s) %s at the building address" % ",".join(dup)
                       if dup else "unlinked site(s) at a different address")
        elif bl:
            verdict = "present as an approved building"
        elif ss or zz:
            verdict = "evidence exists but no approved building - registry review needed"
        else:
            verdict = "no evidence in any source"
        out.append("   SUGGESTED: %s (operator decision required - nothing auto-approved)" % verdict)
    return out


def render(res: dict, *, snap: dict | None = None, targets=(), mode: str = "DRY-RUN") -> str:
    L = []
    names = res["building_names"]
    L.append("=== CANONICAL SERVICE RECONCILIATION (%s) tenant=%s ===" % (mode, res["tenant_id"]))
    L.append("generated_at: %s" % res["generated_at"].isoformat())
    L.append("")
    L.append("=== SOURCES ===")
    for k, s in res["sources"].items():
        L.append(_line(k, *("%s=%s" % (x, y) for x, y in sorted(s.items()))))
    if res["degraded"]:
        L.append("!! DEGRADED: a required source was unavailable - CONFIRMED capped at PROBABLE;"
                 " --apply is always refused (no override)")

    p = res["portfolio"]
    L.append("")
    L.append("=== PORTFOLIO (INTERNAL - not customer-facing) ===")
    L.append("buildings                              %5d" % p["buildings"])
    for t in V.LIFE_SAFETY_TYPES:
        L.append("confirmed %-28s %5d" % (t, p["confirmed_services"].get(t, 0)))
    L.append("confirmed services (counted)           %5d" % p["confirmed_service_total"])
    L.append("required connections (confirmed)       %5d" % p["confirmed_required_connections"])
    L.append("probable services (not counted)        %5d" % p["probable_services"])
    L.append("probable ADDITIONAL connections        %5d" % p["probable_additional_connections"])
    L.append("unresolved life-safety services        %5d" % p["unresolved_services"])
    L.append("unclassified current telephone lines   %5d" % p["unclassified_lines"])
    L.append("unplaced telephone numbers             %5d" % p["unplaced_telephone_numbers"])
    L.append("historical (not current) assets        %5d" % p["historical_assets"])
    if not p["precise_total_available"]:
        L.append("NOTE: unresolved / unclassified records remain - no single precise total is stated.")

    L.append("")
    L.append("=== PER BUILDING ===")
    L.append(_line("building", "suspect", "confirmed services", "required conns",
                   "probable svc (+conns)", "unresolved", "unclassified lines", "historical assets"))
    for b in res["building_summaries"]:
        L.append(_line(b["name"], "SUSPECT" if b["suspect"] else "",
                       ",".join("%s=%d" % kv for kv in sorted(b["confirmed_services"].items())) or "0",
                       b["required_connections"],
                       "%d (+%d)" % (b["probable_services"], b["probable_additional_connections"]),
                       b["unresolved_services"], b["unclassified_lines"], b["historical_assets"]))

    L.append("")
    L.append("=== SERVICES ===")
    for s in sorted(res["services"], key=lambda x: (str(names.get(x["building_id"])), x["service_key"])):
        L.append(_line(names.get(s["building_id"]), s["service_key"], s["service_type"],
                       s["display_name"], s["confidence"], "approval=%s" % s["approval"],
                       s["lifecycle"], "COUNTED" if s["counts"] else "-"))
        if s["service_type"] in V.LIFE_SAFETY_TYPES:
            L.append("     deployment: %s%s  lifecycle_reason=%s  source_status=%s" % (
                s.get("deployment"), " (%s)" % s["deployment_basis"] if s.get("deployment_basis")
                else "", s.get("lifecycle_reason") or "-", s.get("source_status") or "-"))
        pv = s.get("provenance")
        if pv:
            L.append("     provenance: sources=%s napco=%s%s" % (
                ",".join(pv["sources"]) or "-", pv["napco_evidence"],
                " radio=%s" % ",".join(mask(x) for x in pv["radio_ids"]) if pv["radio_ids"] else ""))

    for sr in res["suspect_reports"]:
        L.append("")
        L.append("=== %s RECONCILIATION (BUILDING_IDENTITY_SUSPECT - strict) ===" % str(sr["name"]).upper())
        L.append("confirmed assets (%d): %s" % (len(sr["confirmed_assets"]),
                                                ", ".join(sr["confirmed_assets"]) or "none"))
        L.append("confirmed services (%d): %s" % (len(sr["confirmed_services"]),
                                                  ", ".join(sr["confirmed_services"]) or "none"))
        L.append("-- suspect imported records (legacy association, not confirmed here) --")
        for e in sr["suspect_imports"]:
            L.append(_line(e["record"], e["location_text"], ",".join(e["numbers"]) or "-",
                           "placed=%s (%s/%s)" % (e["placed_to"] or "UNPLACED",
                                                  e["placement_confidence"], e["basis"]),
                           "source candidates=%s" % (",".join(str(x) for x in e["source_building_candidates"]) or "none")))
            L.append("     evidence: %s" % "; ".join(e["evidence"]))
        L.append("-- unmatched / ambiguous --")
        for e in sr["unmatched_or_ambiguous"]:
            L.append(_line(e["record"], e["location_text"], ",".join(e["numbers"]) or "-",
                           e["basis"], e["note"]))
            L.append("     evidence: %s" % "; ".join(e["evidence"]))
        L.append("(nothing moved or deleted - operator decides)")

    L.append("")
    L.append("=== OPERATOR SERVICE POOLS (aggregate knowledge - no per-line class) ===")
    for p in res.get("operator_pools") or []:
        L.append(_line(names.get(p["building_id"]), p["ref"], "/".join(p["service_types"]),
                       "%d lines" % len(p["numbers"]), p.get("label") or "-"))
    L.append("")
    L.append("=== EXCLUDED SOURCE RECORDS (operator disposition - kept for audit) ===")
    for e in res.get("excluded_records") or []:
        L.append(_line(e["record"], e["disposition"],
                       e.get("duplicate_of") or e.get("location") or "-",
                       e.get("location_text") or "-"))
    L.append("")
    L.append("=== LIFECYCLE EVENTS (operator) ===")
    for ev in res["lifecycle_events"]:
        L.append(_line(names.get(ev["building_id"]), ev["event_type"], "effective=%s" % ev.get("effective_at"),
                       "legacy=%d" % len(ev["legacy"]), "replacement=%d" % len(ev["replacement"])))
    L.append("-- historical assets (queryable, never current) --")
    for a in sorted(res["assets"].values(), key=lambda x: x["key"]):
        if a["lifecycle"] in V.NOT_CURRENT:
            L.append(_line(names.get(a["building_id"]), a["asset_type"], a["display_value"],
                           a["lifecycle"], a.get("lifecycle_reason"), a.get("carrier") or "-"))

    L.append("")
    L.append("=== FINDINGS (operator review) ===")
    order = {V.HIGH: 0, V.MEDIUM: 1, V.INFO: 2}
    for f in sorted(res["findings"], key=lambda x: (order.get(x["severity"], 3), x["code"],
                                                    str(x["building"]), str(x["subject"]))):
        L.append(_line(f["severity"], f["code"], f["building"] or "-", f["subject"], f["detail"]))

    if targets and snap is not None:
        L.append("")
        L.append("=== REVIEW WATCHLIST (evidence only - nothing auto-approved) ===")
        L.extend(watchlist(snap, res, targets))
    L.append("")
    L.append("(%s: nothing was written)" % mode if mode == "DRY-RUN" else "(%s)" % mode)
    return "\n".join(L)
