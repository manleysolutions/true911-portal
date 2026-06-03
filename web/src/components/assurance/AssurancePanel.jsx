import { useState, useEffect } from "react";
import { getSiteAssurance } from "@/api/assurance";
import AssuranceBadge from "@/components/assurance/AssuranceBadge";

/**
 * Property-detail Assurance panel. Reusable — can sit at the top of any site
 * detail surface. Reads GET /api/assurance/site/{id}: status, last evaluated,
 * reasons, recommended action. No business logic here; the engine owns it.
 */
export default function AssurancePanel({ siteId }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    let alive = true;
    if (!siteId) return;
    setState({ loading: true, data: null, error: null });
    getSiteAssurance(siteId)
      .then((d) => alive && setState({ loading: false, data: d, error: null }))
      .catch((e) =>
        alive &&
        setState({
          loading: false,
          data: null,
          error: e?.status === 404 ? "Assurance is not enabled for this environment." : (e?.message || "Could not load assurance."),
        })
      );
    return () => { alive = false; };
  }, [siteId]);

  const { loading, data, error } = state;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-gray-800">Assurance Status</h3>
        {data && <AssuranceBadge label={data.assurance_label} size="md" />}
      </div>

      {loading && <div className="mt-3 text-sm text-gray-400">Checking protection status…</div>}
      {error && <div className="mt-3 text-sm text-gray-500">{error}</div>}

      {data && (
        <div className="mt-3 space-y-3">
          {data.statement && <p className="text-sm text-gray-700">{data.statement}</p>}

          <div className="text-xs text-gray-400">
            Last evaluated: {data.as_of ? new Date(data.as_of).toLocaleString() : "—"}
          </div>

          {Array.isArray(data.reasons) && data.reasons.length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-1">What we're looking at</div>
              <ul className="space-y-1">
                {data.reasons.map((r, i) => (
                  <li key={r.code || i} className="text-sm text-gray-700 flex items-start gap-2">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-gray-300 flex-shrink-0" />
                    <span>{r.message || r.code}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.recommended_action && (
            <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
              <div className="text-xs font-medium text-gray-500">Recommended action</div>
              <div className="text-sm text-gray-700">{data.recommended_action}</div>
            </div>
          )}

          {data.disclaimer && (
            <p className="text-[11px] leading-snug text-gray-400">{data.disclaimer}</p>
          )}
        </div>
      )}
    </div>
  );
}
