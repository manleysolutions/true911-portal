import { useEffect, useRef, useState } from "react";
import { motion, animate, useReducedMotion } from "framer-motion";
import {
  Building2, TriangleAlert, OctagonAlert, CircleCheck, CircleDashed, Wrench, Shield, PhoneCall,
  RefreshCw, ChevronRight,
} from "lucide-react";
import { STATUS_TOKENS, E911_IDENTITY, freshnessText, heroChips } from "@/components/customer/commandCenter";

// ════════════════════════════════════════════════════════════════════
// Command Center building blocks — presentation only.  Every status element
// renders an icon AND text; colour comes only from STATUS_TOKENS.
// Motion is restrained and disabled under prefers-reduced-motion; it never
// encodes a state and nothing UNKNOWN is ever animated.
// ════════════════════════════════════════════════════════════════════

export const STATUS_ICON = {
  good: CircleCheck, attention: TriangleAlert, critical: OctagonAlert,
  working: Wrench, unknown: CircleDashed,
};
export const TILE_ICON = { locations: Building2, attention: TriangleAlert, e911: PhoneCall, services: Shield };

export function StatusChip({ token = "unknown", children, className = "" }) {
  const t = STATUS_TOKENS[token] || STATUS_TOKENS.unknown;
  const Icon = STATUS_ICON[token];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${t.chip} ${className}`}>
      {Icon && <Icon className="w-3 h-3 flex-shrink-0" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function E911Badge() {
  return <span className={`inline-flex items-center rounded px-1.5 py-px text-[10px] font-bold tracking-wide ${E911_IDENTITY}`}>E911</span>;
}

// Counts up once on first show; instant under reduced motion.
export function CountUp({ value }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  const last = useRef(0);
  useEffect(() => {
    if (reduce || typeof value !== "number") { setShown(value); last.current = value; return undefined; }
    const from = last.current;
    last.current = value;
    const ctl = animate(from, value, { duration: 0.45, ease: "easeOut", onUpdate: (v) => setShown(Math.round(v)) });
    return () => ctl.stop();
  }, [value, reduce]);
  return <span className="tabular-nums">{shown}</span>;
}

export function StatusStatement({ statement, name, freshness, onRefresh, refreshing, children }) {
  const t = STATUS_TOKENS[statement.tone] || STATUS_TOKENS.unknown;
  const Icon = STATUS_ICON[statement.tone] || CircleDashed;
  return (
    <section aria-labelledby="cc-statement" className="relative overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/80">
      <div className={`absolute inset-y-0 left-0 w-1.5 ${t.accent}`} aria-hidden="true" />
      <div className="px-5 sm:px-7 py-4 lg:py-3 flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-8">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">{name}</p>
          <div className="mt-0.5 flex items-start gap-3">
            <Icon className={`w-7 h-7 mt-0.5 flex-shrink-0 ${t.text}`} aria-hidden="true" />
            <div aria-live="polite">
              <h1 id="cc-statement" className="text-[24px] sm:text-[26px] leading-[1.15] font-semibold tracking-tight text-slate-900">
                {statement.title}
              </h1>
              <p className="mt-0.5 text-[13.5px] leading-5 text-slate-600">{statement.detail}</p>
            </div>
          </div>
          {/* at most 3 summaries; the full breakdown lives in the Action Center */}
          {heroChips(statement).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {heroChips(statement).map((c) => (
                <StatusChip key={c.key} token={c.token}>{c.owner === "customer" ? "For you" : "True911"}: {c.text}</StatusChip>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col sm:flex-row lg:flex-col items-stretch sm:items-center lg:items-end gap-2 lg:gap-1">
          {children}
          <Freshness at={freshness} onRefresh={onRefresh} refreshing={refreshing} />
        </div>
      </div>
    </section>
  );
}

export function Freshness({ at, onRefresh, refreshing }) {
  const reduce = useReducedMotion();
  return (
    <div className="flex items-center gap-2 text-[11.5px] text-slate-500">
      <motion.span key={at ? at.getTime() : "none"} initial={reduce ? false : { opacity: 0.35 }} animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }} className="tabular-nums">
        {freshnessText(at)}
      </motion.span>
      <button type="button" onClick={onRefresh} disabled={refreshing} aria-label="Refresh now"
        className="cc-focus inline-flex items-center justify-center w-9 h-9 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-50">
        <RefreshCw className="w-4 h-4" aria-hidden="true" />
      </button>
    </div>
  );
}

export function OpTile({ tile, onClick, index = 0 }) {
  const reduce = useReducedMotion();
  const t = STATUS_TOKENS[tile.token] || STATUS_TOKENS.neutral;
  const Icon = TILE_ICON[tile.icon];
  const interactive = Boolean(onClick);
  const Body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <span className={`inline-flex w-9 h-9 items-center justify-center rounded-xl ${tile.token === "neutral" ? "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200" : t.chip}`}>
            {Icon && <Icon className="w-5 h-5" strokeWidth={1.9} aria-hidden="true" />}
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">{tile.title}</span>
        </span>
        {tile.e911 && <E911Badge />}
      </div>
      <span className={`mt-2 block h-0.5 w-8 rounded-full ${tile.token === "neutral" ? "bg-slate-200" : t.accent}`} aria-hidden="true" />
      <div className="mt-2">
        {tile.numeric ? (
          <p className={`text-[34px] leading-none font-bold tracking-tight ${tile.token === "neutral" ? "text-slate-900" : t.text}`}>
            <CountUp value={tile.value} />
            {tile.caption && <span className="ml-2 text-[13px] font-medium tracking-normal text-slate-600">{tile.caption}</span>}
          </p>
        ) : (
          <p className={`text-[19px] leading-snug font-semibold tracking-tight ${tile.token === "neutral" ? "text-slate-900" : t.text}`}>{tile.value}</p>
        )}
        <p className="mt-1 text-[12px] text-slate-500 leading-snug">{tile.detail}</p>
      </div>
      {interactive && <ChevronRight className="absolute right-3 bottom-3 w-4 h-4 text-slate-300" aria-hidden="true" />}
    </>
  );
  const cls = `relative text-left rounded-2xl bg-white px-4 py-3.5 sm:px-5 lg:py-3.5 shadow-sm ring-1 ${t.tile} ${interactive ? "cc-focus hover:shadow-md transition-shadow" : ""}`;
  return (
    <motion.div initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: reduce ? 0 : index * 0.04 }} className="h-full">
      {interactive
        ? <button type="button" onClick={onClick} className={`${cls} w-full h-full`} aria-label={`${tile.title}: ${tile.value}${tile.caption ? ` ${tile.caption}` : ""}. ${tile.detail}`}>{Body}</button>
        : <div className={`${cls} h-full`}>{Body}</div>}
    </motion.div>
  );
}

// Static skeleton — no looping shimmer (life-safety UI never pulses for nothing).
function Bone({ className = "" }) {
  return <div className={`rounded-lg bg-slate-200/70 ${className}`} />;
}
export function CommandSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-label="Loading your command center">
      <div className="rounded-2xl bg-white ring-1 ring-slate-200/80 p-6 space-y-3">
        <Bone className="h-3 w-40" /><Bone className="h-7 w-80 max-w-full" /><Bone className="h-3 w-96 max-w-full" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-2xl bg-white ring-1 ring-slate-200/80 p-5 space-y-3"><Bone className="h-3 w-24" /><Bone className="h-8 w-16" /><Bone className="h-3 w-32" /></div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8 rounded-2xl bg-white ring-1 ring-slate-200/80 h-[420px] lg:h-[460px] p-5"><Bone className="h-full w-full" /></div>
        <div className="lg:col-span-4 rounded-2xl bg-white ring-1 ring-slate-200/80 p-5 space-y-3">{[0, 1, 2, 3].map((i) => <Bone key={i} className="h-10 w-full" />)}</div>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
