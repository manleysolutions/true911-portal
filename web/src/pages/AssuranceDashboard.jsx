import { useState, useEffect, useMemo } from "react";
import { ShieldCheck } from "lucide-react";

import { config } from "@/config";
import { loadPortfolioAssurance } from "@/api/assurance";
import { summarizePortfolio } from "@/lib/assuranceStatus";
import AssuranceSummaryCards from "@/components/assurance/AssuranceSummaryCards";
import ExecutiveSummaryWidget from "@/components/assurance/ExecutiveSummaryWidget";
import AssurancePropertyList from "@/components/assurance/AssurancePropertyList";
import AssurancePanel from "@/components/assurance/AssurancePanel";

/**
 * Customer Assurance Dashboard — protection status across the tenant's
 * locations. Consumes the read-only /api/assurance endpoints only; all label
 * logic lives in the backend engine.
 *
 * Gated by config.featureAssuranceDashboard (VITE_FEATURE_ASSURANCE_DASHBOARD).
 * Even if reached directly, it renders a "not enabled" state when off.
 */
export default function AssuranceDashboard() {
  const [state, setState] = useState({ loading: true, rows: [], error: null });
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    if (!config.featureAssuranceDashboard) return;
    let alive = true;
    setState({ loading: true, rows: [], error: null });
    loadPortfolioAssurance()
      .then((rows) => alive && setState({ loading: false, rows, error: null }))
      .catch((e) => alive && setState({ loading: false, rows: [], error: e?.message || "Could not load assurance." }));
    return () => { alive = false; };
  }, []);

  const counts = useMemo(() => summarizePortfolio(state.rows), [state.rows]);
  const allUnavailable = state.rows.length > 0 && state.rows.every((r) => r.error === "unavailable");

  if (!config.featureAssuranceDashboard) {
    return <NotEnabled />;
  }

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-5 h-5 text-green-600" />
        <h1 className="text-xl font-semibold text-gray-900">Assurance</h1>
      </div>
      <p className="text-sm text-gray-500 -mt-3">
        Protection status across your locations — whether emergency communication is ready.
      </p>

      {state.loading && <div className="text-sm text-gray-400">Loading protection status…</div>}

      {!state.loading && state.error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {state.error}
        </div>
      )}

      {!state.loading && !state.error && allUnavailable && (
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500">
          Assurance is not enabled for this environment yet.
        </div>
      )}

      {!state.loading && !state.error && !allUnavailable && (
        <>
          <AssuranceSummaryCards counts={counts} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="lg:col-span-2 space-y-4">
              <AssurancePropertyList
                rows={state.rows}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
              {selectedId && <AssurancePanel siteId={selectedId} />}
            </div>
            <div className="space-y-4">
              <ExecutiveSummaryWidget counts={counts} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function NotEnabled() {
  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-8 text-center">
        <ShieldCheck className="w-6 h-6 text-gray-400 mx-auto mb-2" />
        <div className="text-sm font-medium text-gray-700">Assurance Dashboard is not enabled</div>
        <div className="text-xs text-gray-400 mt-1">
          Set VITE_FEATURE_ASSURANCE_DASHBOARD=true (and FEATURE_ASSURANCE_ENGINE on the API) to enable.
        </div>
      </div>
    </div>
  );
}
