import { ChevronRight } from "lucide-react";
import { actionCenterHeadline, actionCenterTiers } from "@/components/customer/selfService";

// ════════════════════════════════════════════════════════════════════
// ActionCenter — "What needs your attention", tiered by urgency AND owner:
//   Urgent        — known service problems (evidence-backed only)
//   Action needed — things the customer can do now (E911 confirmations, replies)
//   In progress   — True911 / operations own these (records being prepared,
//                   monitoring records being confirmed, requests being worked)
//   Portfolio setup — optional completion (site contacts), collapsed
//   Recent activity — history only; nothing waits on it (D-028)
// Missing contacts are never shown at the severity of a service problem, and the
// customer is never made responsible for True911's work.
// Presentational: the dashboard loads GET /customer/action-center once and
// passes it in (null when self-service is off → renders nothing).
// ════════════════════════════════════════════════════════════════════

const TIER_STYLE = {
  urgent: { badge: "bg-red-50 text-red-700 border-red-200", title: "text-red-800" },
  action_needed: { badge: "bg-amber-50 text-amber-800 border-amber-200", title: "text-slate-900" },
  in_progress: { badge: "bg-slate-50 text-slate-600 border-slate-200", title: "text-slate-900" },
  informational: { badge: "bg-slate-50 text-slate-500 border-slate-200", title: "text-slate-700" },
  activity: { badge: "bg-slate-50 text-slate-500 border-slate-200", title: "text-slate-700" },
};

function Rows({ section, onOpen }) {
  const { title, subtitle, items, row, action, noOpen } = section;
  return (
    <div className="py-2">
      <div className="flex items-baseline gap-2 px-1">
        <p className="text-[12px] font-medium text-slate-800">{title}</p>
        <span className="text-[11px] text-slate-400 tabular-nums">{items.length}</span>
      </div>
      {subtitle && <p className="text-[11px] text-slate-400 px-1">{subtitle}</p>}
      <div className="mt-1 rounded-lg border border-slate-100 divide-y divide-slate-100 max-h-44 overflow-y-auto">
        {items.slice(0, 25).map((it, i) => (
          noOpen || !it.location_ref ? (
            <div key={i} className="px-3 py-1.5 text-[12px] text-slate-600 truncate">{row(it)}</div>
          ) : (
            <button key={i} type="button"
              onClick={() => onOpen({ ref: it.location_ref, name: it.location, intent: action?.intent || null })}
              className="w-full text-left px-3 py-1.5 hover:bg-slate-50 flex items-center gap-2">
              <span className="text-[12px] text-slate-800 flex-1 min-w-0 truncate">{row(it)}</span>
              {action && <span className="text-[11px] font-medium text-slate-600 flex-shrink-0">{action.label}</span>}
              <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
            </button>
          )
        ))}
      </div>
    </div>
  );
}

export default function ActionCenter({ data, onOpenLocation }) {
  if (!data) return null;
  const tiers = actionCenterTiers(data);
  return (
    <section aria-labelledby="action-center-title" className="bg-white rounded-xl border border-slate-200">
      <div className="px-5 py-3.5 border-b border-slate-100">
        <h2 id="action-center-title" className="text-[13px] font-semibold text-slate-900">What needs your attention</h2>
        <p className="text-[11.5px] text-slate-500">{actionCenterHeadline({
          ...data.counts, awaiting_your_response: (data.awaiting_your_response || []).length })}</p>
      </div>
      <div className="divide-y divide-slate-100">
        {tiers.map((t) => (
          <details key={t.tier} open={t.open} className="group px-5 py-2.5">
            <summary className="flex items-center gap-2 cursor-pointer list-none select-none">
              <ChevronRight className="w-3.5 h-3.5 text-slate-400 transition-transform group-open:rotate-90" />
              <span className={`text-[12.5px] font-semibold ${TIER_STYLE[t.tier].title}`}>{t.title}</span>
              <span className="text-[11px] text-slate-400 hidden sm:inline">· {t.subtitle}</span>
              {t.count > 0 && <span className={`ml-auto text-[11px] font-semibold tabular-nums border rounded-full px-2 py-0.5 ${TIER_STYLE[t.tier].badge}`}>{t.count}</span>}
            </summary>
            <div className="pl-5">
              {t.sections.map((s) => <Rows key={s.key} section={s} onOpen={onOpenLocation} />)}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
