/**
 * Samantha — LLLM Phase 1 internal-only AI Health Summary console.
 *
 * The page lives behind config.featureLllm AND the backend
 * VIEW_AI_SUMMARY + internal-context gate (see
 * api/app/routers/llm.py).  When the flag is off, the AIHealthSummary
 * component renders nothing and this page falls back to the "Coming
 * Soon" placeholder so a customer-tenant Admin who lands here via
 * direct URL doesn't see anything operational.
 *
 * Scope picker:
 *   - Fleet      → tenant-wide summary
 *   - Site       → one site (enter the site_id)
 *   - Device     → reserved for Phase 2 (disabled in Phase 1)
 */

import { useState } from "react";
import { Sparkles, Building2, Globe2, Cpu } from "lucide-react";

import PageWrapper from "@/components/PageWrapper";
import AIHealthSummary from "@/components/AIHealthSummary";
import { config } from "@/config";

const SCOPES = [
  {
    key: "fleet",
    label: "Fleet",
    icon: Globe2,
    description: "Tenant-wide summary across every site and device.",
    needsId: false,
  },
  {
    key: "site",
    label: "Site",
    icon: Building2,
    description: "One site, by site_id.",
    needsId: true,
  },
  {
    key: "device",
    label: "Device",
    icon: Cpu,
    description: "Reserved for Phase 2.",
    needsId: true,
    disabled: true,
  },
];

function ComingSoonStub() {
  return (
    <PageWrapper>
      <div className="p-6 max-w-3xl mx-auto">
        <div className="text-center py-20">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-purple-100 rounded-2xl mb-4">
            <Sparkles className="w-8 h-8 text-purple-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Samantha AI</h1>
          <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto">
            AI-assisted onboarding, anomaly detection, and natural language event
            queries. This feature is coming soon.
          </p>
          <div className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-purple-50 border border-purple-200 rounded-xl text-sm text-purple-700 font-medium">
            <Sparkles className="w-4 h-4" />
            Coming Soon
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}

export default function Samantha() {
  const [scope, setScope] = useState("fleet");
  const [siteIdInput, setSiteIdInput] = useState("");
  const [committedSiteId, setCommittedSiteId] = useState("");

  // When the flag is off, fall back to the original placeholder so a
  // customer-tenant Admin who lands here via direct URL doesn't see
  // anything operational.  The AIHealthSummary itself ALSO checks the
  // flag — defense in depth.
  if (!config.featureLllm) {
    return <ComingSoonStub />;
  }

  const activeScope = SCOPES.find((s) => s.key === scope) || SCOPES[0];
  const resolvedScopeId =
    activeScope.key === "site" ? committedSiteId || undefined : undefined;
  const ready =
    activeScope.key === "fleet" ||
    (activeScope.key === "site" && committedSiteId);

  return (
    <PageWrapper>
      <div className="p-6 max-w-4xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-purple-600 rounded-xl flex items-center justify-center shadow-sm">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900 tracking-tight">
              AI Health Summary
            </h1>
            <p className="text-[11px] text-gray-500">
              Read-only · Internal use · Phase 1 MVP
            </p>
          </div>
        </div>

        {/* Scope picker */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-[0.08em] mb-2">
            Scope
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {SCOPES.map((s) => {
              const Icon = s.icon;
              const isActive = scope === s.key;
              const isDisabled = !!s.disabled;
              return (
                <button
                  key={s.key}
                  type="button"
                  disabled={isDisabled}
                  onClick={() => {
                    if (isDisabled) return;
                    setScope(s.key);
                    if (s.key !== "site") setCommittedSiteId("");
                  }}
                  className={`text-left rounded-lg border px-3 py-2.5 transition-colors ${
                    isDisabled
                      ? "border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed"
                      : isActive
                        ? "border-purple-300 bg-purple-50 text-purple-900"
                        : "border-gray-200 bg-white hover:bg-gray-50 text-gray-800"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Icon
                      className={`w-3.5 h-3.5 ${
                        isActive ? "text-purple-600" : "text-gray-500"
                      }`}
                    />
                    <span className="text-[13px] font-semibold">{s.label}</span>
                  </div>
                  <p
                    className={`text-[11px] leading-snug ${
                      isActive ? "text-purple-800/80" : "text-gray-500"
                    }`}
                  >
                    {s.description}
                  </p>
                </button>
              );
            })}
          </div>

          {/* Site id input — only when scope is "site" */}
          {scope === "site" && (
            <form
              className="mt-3 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setCommittedSiteId(siteIdInput.trim());
              }}
            >
              <input
                value={siteIdInput}
                onChange={(e) => setSiteIdInput(e.target.value)}
                placeholder="site_id (e.g. site-abc123)"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                maxLength={100}
              />
              <button
                type="submit"
                disabled={!siteIdInput.trim()}
                className="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:opacity-40"
              >
                Load
              </button>
            </form>
          )}
        </div>

        {/* Summary panel */}
        {ready ? (
          <AIHealthSummary
            scope={activeScope.key}
            scopeId={resolvedScopeId}
            title={
              activeScope.key === "fleet"
                ? "Tenant Fleet Summary"
                : `Site ${resolvedScopeId} Summary`
            }
            theme="light"
          />
        ) : (
          <div className="bg-white rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
            Enter a site_id above and click Load.
          </div>
        )}

        {/* Footer note */}
        <p className="text-[11px] text-gray-500 leading-relaxed">
          AI summaries are read-only and based solely on existing structured
          telemetry. Every call writes an audit-log row (see{" "}
          <code className="text-[10px] bg-gray-100 px-1 py-0.5 rounded">
            llm_audit_log
          </code>
          ) and respects the per-tenant daily token cap. See
          <code className="text-[10px] bg-gray-100 px-1 py-0.5 rounded ml-1">
            docs/AI_OPERATIONAL_SAFETY.md
          </code>{" "}
          for the full governance contract.
        </p>
      </div>
    </PageWrapper>
  );
}
