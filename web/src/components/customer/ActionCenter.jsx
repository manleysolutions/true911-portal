import { useId, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ChevronRight, TriangleAlert, UserCheck, Wrench, ListChecks, History } from "lucide-react";
import { actionCenterHeadline, actionCenterTiers } from "@/components/customer/selfService";
import { STATUS_TOKENS, ownership, summarizeTiers, actionTotal } from "@/components/customer/commandCenter";

// ════════════════════════════════════════════════════════════════════
// ActionCenter — "What needs your attention", tiered by urgency AND owner:
//   Urgent        — known service problems (evidence-backed only)
//   Action needed — things the customer can do now (E911 confirmations, replies)
//   In progress   — True911 / operations own these (records being prepared,
//                   monitoring records being confirmed, requests being worked);
//                   each row says who acted and who owns the next step
//   Portfolio setup — optional completion (site contacts), collapsed
//   Recent activity — history only; nothing waits on it (D-028)
// Missing contacts are never shown at the severity of a service problem, and the
// customer is never made responsible for True911's work.
// Presentational: the dashboard loads GET /customer/action-center once and
// passes it in (null when self-service is off → renders nothing).
// mode="summary" (Overview rail): operational tiers only, first items + totals,
// "View all" to the full view — no nested scrolling.  mode="full" (Action
// Center view): every tier, every item.
// ════════════════════════════════════════════════════════════════════

// Tier -> owner icon + count-chip token.  Only "Action needed" is the customer's.
const TIER_LOOK = {
  urgent: { icon: TriangleAlert, token: "critical" },
  action_needed: { icon: UserCheck, token: "attention" },
  in_progress: { icon: Wrench, token: "working" },
  informational: { icon: ListChecks, token: "neutral" },
  activity: { icon: History, token: "neutral" },
};

// Ownership tag shown on every row: the customer's work and True911's work must
// never look alike (icon + word + colour; colour is never the only signal).
const OWNER_TAG = {
  customer: { icon: UserCheck, word: "Your action", text: "text-amber-900", rule: "before:bg-amber-400" },
  true911: { icon: Wrench, word: "True911", text: "text-blue-800", rule: "before:bg-blue-400" },
};

function OwnerLine({ own }) {
  if (!own.text) return null;
  const tag = OWNER_TAG[own.owner];
  if (!tag) return <span className="block text-[11.5px] mt-0.5 text-slate-500">{own.text}</span>;
  const Icon = tag.icon;
  return (
    <span className={`mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11.5px] leading-snug ${tag.text}`}>
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <Icon className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
        <span className="font-semibold uppercase tracking-[0.06em] text-[10.5px]">{tag.word}</span>
        <span aria-hidden="true">·</span>
      </span>
      <span className="min-w-0">{own.text}</span>
    </span>
  );
}

function Rows({ section, onOpen, compact }) {
  const { title, subtitle, items, row, action, noOpen, key } = section;
  const total = section.total ?? items.length;
  return (
    <div className={compact ? "py-1.5" : "py-3"}>
      <div className="flex items-baseline gap-2">
        <p className="text-[12.5px] font-medium text-slate-800">{title}</p>
        <span className="text-[11px] text-slate-400 tabular-nums">{total}</span>
      </div>
      {subtitle && !compact && <p className="text-[11.5px] text-slate-500 leading-snug mt-0.5">{subtitle}</p>}
      <ul className={`${compact ? "mt-1" : "mt-2"} rounded-xl ring-1 ring-slate-100 divide-y divide-slate-100`}>
        {items.map((it, i) => {
          const own = ownership(key, it);
          const ownLine = <OwnerLine own={own} />;
          const rule = OWNER_TAG[own.owner]?.rule;
          const ruleCls = rule ? `relative before:absolute before:left-0 before:top-2 before:bottom-2 before:w-0.5 before:rounded-full ${rule}` : "";
          return (
            <li key={i}>
              {noOpen || !it.location_ref ? (
                <div className="px-3.5 py-2.5 text-[12.5px] text-slate-600"><span className="block truncate">{row(it)}</span></div>
              ) : (
                <button type="button"
                  onClick={() => onOpen({ ref: it.location_ref, name: it.location, intent: action?.intent || null })}
                  className={`cc-focus w-full text-left px-3.5 ${compact ? "py-1.5 min-h-[44px]" : "py-2.5 min-h-[48px]"} hover:bg-slate-50 flex items-center gap-2 ${ruleCls}`}>
                  <span className="flex-1 min-w-0">
                    <span className="block text-[12.5px] text-slate-800 truncate">{row(it)}</span>
                    {ownLine}
                  </span>
                  {/* a BUTTON only where the customer must act; otherwise a quiet link to the location */}
                  {action && (own.owner === "customer"
                    ? <span className="text-[11.5px] font-semibold text-slate-900 flex-shrink-0 rounded-md px-2 py-1 ring-1 ring-inset ring-slate-300">{action.label}</span>
                    : <span className="text-[11.5px] text-slate-500 flex-shrink-0">{action.label}</span>)}
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" aria-hidden="true" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {section.hidden > 0 && <p className="mt-1 text-[11px] text-slate-500 tabular-nums">+{section.hidden} more</p>}
    </div>
  );
}

function Tier({ t, onOpen, compact }) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(Boolean(t.open));
  const panelId = useId();
  const look = TIER_LOOK[t.tier] || TIER_LOOK.informational;
  const Icon = look.icon;
  const tok = STATUS_TOKENS[look.token];
  const actionable = t.tier === "action_needed" && t.count > 0;
  return (
    <div className={`px-4 sm:px-5 ${compact ? "py-2" : "py-3.5"}`}>
      <h3>
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls={panelId}
          className={`cc-focus w-full flex items-center gap-2.5 ${compact ? "min-h-[40px]" : "min-h-[44px]"} text-left rounded-lg`}>
          <span className={`inline-flex w-7 h-7 items-center justify-center rounded-lg flex-shrink-0 ${look.token === "neutral" ? "bg-slate-100 text-slate-500" : tok.chip}`}>
            <Icon className="w-3.5 h-3.5" aria-hidden="true" />
          </span>
          <span className="flex-1 min-w-0">
            <span className="block text-[13px] font-semibold text-slate-900">{t.title}</span>
            {!compact && <span className="block text-[11.5px] text-slate-500 truncate">{t.subtitle}</span>}
          </span>
          {t.count > 0 && (
            // one-time emphasis on genuinely actionable work; never loops
            <motion.span initial={actionable && !reduce ? { scale: 0.8 } : false} animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 420, damping: 18 }}
              className={`text-[11.5px] font-semibold tabular-nums rounded-full px-2 py-0.5 ${tok.chip}`}>
              {t.count}<span className="sr-only"> items</span>
            </motion.span>
          )}
          <ChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden="true" />
        </button>
      </h3>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div id={panelId} key="panel"
            initial={reduce ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={reduce ? undefined : { height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="pl-[38px]">
              {t.sections.map((s) => <Rows key={s.key} section={s} onOpen={onOpen} compact={compact} />)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function ActionCenter({ data, onOpenLocation, mode = "full", onViewAll }) {
  if (!data) return null;
  const all = actionCenterTiers(data);
  const summary = mode === "summary";
  const tiers = summary ? summarizeTiers(all) : all.map((t) => ({ ...t, open: t.tier === "activity" ? t.open : true }));
  const waiting = actionTotal(all);
  return (
    <section aria-labelledby="action-center-title" className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80">
      <div className={`px-4 sm:px-5 ${summary ? "pt-3 pb-2.5" : "pt-4 pb-3"} border-b border-slate-100 flex items-start justify-between gap-3`}>
        <div className="min-w-0">
          <h2 id="action-center-title" className={`${summary ? "text-[13.5px]" : "text-[16px]"} font-semibold text-slate-900`}>
            {summary ? "What needs your attention" : "Action Center"}
          </h2>
          {/* the summary rail lets the tiers carry the counts; the full view states them */}
          {!summary && <p className="text-[12px] text-slate-600 mt-0.5">{actionCenterHeadline({
            ...data.counts, awaiting_your_response: (data.awaiting_your_response || []).length })}</p>}
        </div>
      </div>
      <div className="divide-y divide-slate-100">
        {tiers.map((t) => <Tier key={t.tier} t={t} onOpen={onOpenLocation} compact={summary} />)}
      </div>
      {summary && onViewAll && (
        <div className="px-4 sm:px-5 py-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-x-3">
          <a href="?view=actions" onClick={(e) => { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); onViewAll(); }}
            className="cc-focus inline-flex items-center gap-1 min-h-[36px] text-[12.5px] font-semibold text-slate-900 hover:underline">
            {waiting > 0 ? `View all ${waiting} actions` : "Open the Action Center"}
            <ChevronRight className="w-4 h-4" aria-hidden="true" />
          </a>
          <span className="text-[11px] text-slate-500">Includes setup and recent activity</span>
        </div>
      )}
    </section>
  );
}
