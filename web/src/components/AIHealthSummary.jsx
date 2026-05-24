/**
 * AIHealthSummary — internal-only card for LLLM Phase 1.
 *
 * Reusable in multiple surfaces:
 *   - As a standalone panel on the Samantha page (with a scope picker).
 *   - As an additive card on the Command Center, below the existing
 *     IntelligenceBanner.  Does NOT replace the deterministic banner.
 *
 * Renders identically whether the backend returned a fresh LLM-generated
 * payload or the deterministic fallback — operator should not have to
 * care which.  A small subtle pill shows source: "AI" / "cached" /
 * "rules-based" so an audit-minded reader can tell.
 *
 * Hard guarantees of the component:
 *   - Hidden when config.featureLllm is false (defense in depth — the
 *     backend already returns 404, but this avoids even attempting
 *     the request).
 *   - Shows a clean empty/loading state.  Network errors are NOT
 *     surfaced as red banners (the surface is internal-only and the
 *     deterministic fallback is what we render on any failure).
 */

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Sparkles, ShieldAlert, Database, Clock } from "lucide-react";

import { config } from "@/config";
import { getHealthSummary, refreshHealthSummary } from "@/api/llm";

function SourcePill({ source, model, deterministicFallback }) {
  // Three states an operator might want to distinguish:
  //   - cache hit
  //   - fresh provider call
  //   - deterministic fallback (no provider, or provider failed)
  if (deterministicFallback) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold border border-slate-300 bg-slate-50 text-slate-600">
        <Database className="w-2.5 h-2.5" /> rules-based
      </span>
    );
  }
  if (source === "cache") {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold border border-blue-200 bg-blue-50 text-blue-700">
        <Clock className="w-2.5 h-2.5" /> cached
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-semibold border border-purple-200 bg-purple-50 text-purple-700">
      <Sparkles className="w-2.5 h-2.5" /> AI · {model || "model"}
    </span>
  );
}

function ConfidenceBar({ value }) {
  // 0-1 confidence rendered as a thin bar.  Colors mirror the
  // existing status palette (emerald / amber / slate) so it doesn't
  // introduce a new visual vocabulary.
  const pct = Math.round((value || 0) * 100);
  const tone =
    pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 rounded-full bg-slate-200/70 overflow-hidden">
        <div className={`h-1 rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-500 tabular-nums w-8 text-right">
        {pct}%
      </span>
    </div>
  );
}

/**
 * @param {Object} props
 * @param {"fleet"|"site"|"device"} props.scope
 * @param {string|undefined} props.scopeId   required when scope==="site"
 * @param {string|undefined} props.title     header text override
 * @param {"dark"|"light"} props.theme       which palette to use
 */
export default function AIHealthSummary({
  scope = "fleet",
  scopeId,
  title,
  theme = "light",
}) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(
    async ({ force = false } = {}) => {
      setLoading(true);
      setError(null);
      try {
        const fn = force ? refreshHealthSummary : getHealthSummary;
        const data = await fn({ scope, scopeId });
        setSummary(data);
      } catch (err) {
        // A 404 here means FEATURE_LLLM is off — silently no-op
        // because the surface is supposed to be invisible.
        if (err?.status === 404) {
          setSummary(null);
        } else {
          // Any other error → keep showing the last summary (if any)
          // and surface a small inline note.  Internal-only surface,
          // so a tiny diagnostic line is acceptable.
          setError(err?.message || "Unable to load AI summary");
        }
      } finally {
        setLoading(false);
      }
    },
    [scope, scopeId],
  );

  useEffect(() => {
    if (!config.featureLllm) return;
    load();
  }, [load]);

  // Defense-in-depth: hidden when the flag is off, regardless of any
  // backend misconfiguration.
  if (!config.featureLllm) return null;
  // Site scope without an id is a programmer error — render nothing.
  if (scope === "site" && !scopeId) return null;

  const darkPalette =
    "bg-slate-900/80 rounded-xl border border-slate-800/60 text-slate-200";
  const lightPalette =
    "bg-white rounded-xl border border-gray-200 text-gray-900";
  const containerCls = theme === "dark" ? darkPalette : lightPalette;

  const labelCls =
    theme === "dark"
      ? "text-[10px] font-semibold text-slate-500 uppercase tracking-[0.08em]"
      : "text-[10px] font-semibold text-gray-500 uppercase tracking-[0.08em]";
  const bodyCls =
    theme === "dark" ? "text-[13px] text-slate-200 leading-relaxed" : "text-[13px] text-gray-800 leading-relaxed";
  const subCls = theme === "dark" ? "text-[12px] text-slate-400" : "text-[12px] text-gray-600";

  return (
    <div className={`${containerCls} overflow-hidden`}>
      <div
        className={`px-5 py-3 flex items-center gap-2 border-b ${
          theme === "dark" ? "border-slate-800/40" : "border-gray-100"
        }`}
      >
        <Sparkles
          className={`w-4 h-4 ${theme === "dark" ? "text-purple-400" : "text-purple-600"}`}
        />
        <h3
          className={`text-sm font-semibold ${theme === "dark" ? "text-white" : "text-gray-900"}`}
        >
          {title || "AI Health Summary"}
        </h3>
        <span className={`text-[10px] uppercase tracking-wider ml-1 ${
          theme === "dark" ? "text-slate-500" : "text-gray-400"
        }`}>
          internal
        </span>
        <div className="ml-auto flex items-center gap-2">
          {summary && (
            <SourcePill
              source={summary.source}
              model={summary.model}
              deterministicFallback={summary.deterministic_fallback}
            />
          )}
          <button
            type="button"
            onClick={() => load({ force: true })}
            disabled={loading}
            className={`p-1.5 rounded transition-colors ${
              theme === "dark"
                ? "hover:bg-slate-800 text-slate-400"
                : "hover:bg-gray-100 text-gray-500"
            } ${loading ? "opacity-50" : ""}`}
            aria-label="Refresh AI summary"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      <div className="p-5 space-y-3">
        {loading && !summary && (
          <p className={subCls}>Generating summary…</p>
        )}
        {error && (
          <div
            className={`flex items-start gap-2 text-[12px] ${
              theme === "dark" ? "text-amber-300" : "text-amber-700"
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {summary && (
          <>
            <div>
              <div className={labelCls}>Current status</div>
              <p className={`${bodyCls} mt-1`}>{summary.current_status}</p>
            </div>
            {summary.likely_issue && (
              <div>
                <div className={labelCls}>Likely issue</div>
                <p className={`${bodyCls} mt-1`}>{summary.likely_issue}</p>
              </div>
            )}
            <div>
              <div className={labelCls}>Recommended next step</div>
              <p className={`${bodyCls} mt-1`}>{summary.recommended_next_step}</p>
            </div>
            <div>
              <div className={labelCls}>Confidence</div>
              <div className="mt-1">
                <ConfidenceBar value={summary.confidence} />
              </div>
            </div>
            {summary.sources_used?.length > 0 && (
              <div>
                <div className={labelCls}>Sources used</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {summary.sources_used.map((s) => (
                    <span
                      key={s}
                      className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${
                        theme === "dark"
                          ? "bg-slate-800 text-slate-400 border border-slate-700"
                          : "bg-gray-100 text-gray-600 border border-gray-200"
                      } font-mono`}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
