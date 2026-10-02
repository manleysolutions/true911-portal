import { useId, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ChevronRight, TriangleAlert, UserCheck, Wrench, ListChecks, History } from "lucide-react";
import { actionCenterHeadline, actionCenterTiers } from "@/components/customer/selfService";
import { STATUS_TOKENS, ownership } from "@/components/customer/commandCenter";

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
// ════════════════════════════════════════════════════════════════════

// Tier -> owner icon + count-chip token.  Only "Action needed" is the customer's.
const TIER_LOOK = {
  urgent: { icon: TriangleAlert, token: "critical" },
  action_needed: { icon: UserCheck, token: "attention" },
  in_progress: { icon: Wrench, token: "working" },
  informational: { icon: ListChecks, token: "neutral" },
  activity: { icon: History, token: "neutral" },
};

function Rows({ section, onOpen }) {
  const { title, subtitle, items, row, action, noOpen, key } = section;
  return (
    <div className="py-2">
      <div className="flex items-baseline gap-2">
        <p className="text-[12.5px] font-medium text-slate-800">{title}</p>
        <span className="text-[11px] text-slate-400 tabular-nums">{items.length}</span>
      </div>
      {subtitle && <p className="text-[11.5px] text-slate-500 leading-snug">{subtitle}</p>}
      <ul className="mt-1.5 rounded-xl ring-1 ring-slate-100 divide-y divide-slate-100 max-h-56 overflow-y-auto">
        {items.slice(0, 25).map((it, i) => {
          const own = ownership(key, it);
          const ownLine = own.text && (
            <span className={`block text-[11px] mt-0.5 ${STATUS_TOKENS[own.token]?.text || "text-slate-500"}`}>{own.text}</span>
          );
          return (
            <li key={i}>
              {noOpen || !it.location_ref ? (
                <div className="px-3 py-2 text-[12.5px] text-slate-600"><span className="block truncate">{row(it)}</span></div>
              ) : (
                <button type="button"
                  onClick={() => onOpen({ ref: it.location_ref, name: it.location, intent: action?.intent || null })}
                  className="cc-focus w-full text-left px-3 py-2 min-h-[44px] hover:bg-slate-50 flex items-center gap-2">
                  <span className="flex-1 min-w-0">
                    <span className="block text-[12.5px] text-slate-800 truncate">{row(it)}</span>
                    {ownLine}
                  </span>
                  {action && <span className="text-[11.5px] font-semibold text-slate-900 flex-shrink-0 rounded-md px-2 py-1 ring-1 ring-inset ring-slate-300">{action.label}</span>}
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" aria-hidden="true" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Tier({ t, onOpen }) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(Boolean(t.open));
  const panelId = useId();
  const look = TIER_LOOK[t.tier] || TIER_LOOK.informational;
  const Icon = look.icon;
  const tok = STATUS_TOKENS[look.token];
  const actionable = t.tier === "action_needed" && t.count > 0;
  return (
    <div className="px-4 sm:px-5 py-2.5">
      <h3>
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls={panelId}
          className="cc-focus w-full flex items-center gap-2.5 min-h-[44px] text-left rounded-lg">
          <span className={`inline-flex w-7 h-7 items-center justify-center rounded-lg flex-shrink-0 ${look.token === "neutral" ? "bg-slate-100 text-slate-500" : tok.chip}`}>
            <Icon className="w-3.5 h-3.5" aria-hidden="true" />
          </span>
          <span className="flex-1 min-w-0">
            <span className="block text-[13px] font-semibold text-slate-900">{t.title}</span>
            <span className="block text-[11.5px] text-slate-500 truncate">{t.subtitle}</span>
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
              {t.sections.map((s) => <Rows key={s.key} section={s} onOpen={onOpen} />)}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function ActionCenter({ data, onOpenLocation }) {
  if (!data) return null;
  const tiers = actionCenterTiers(data);
  return (
    <section aria-labelledby="action-center-title" className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80">
      <div className="px-4 sm:px-5 pt-4 pb-3 border-b border-slate-100">
        <h2 id="action-center-title" className="text-[14px] font-semibold text-slate-900">What needs your attention</h2>
        <p className="text-[12px] text-slate-600 mt-0.5">{actionCenterHeadline({
          ...data.counts, awaiting_your_response: (data.awaiting_your_response || []).length })}</p>
      </div>
      <div className="divide-y divide-slate-100">
        {tiers.map((t) => <Tier key={t.tier} t={t} onOpen={onOpenLocation} />)}
      </div>
    </section>
  );
}
