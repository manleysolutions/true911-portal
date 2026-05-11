/**
 * Convert-registration modal (Phase R4 frontend).
 *
 * The reviewer fills out the tenant + customer choice and confirms.
 * The modal wraps the backend's two-step contract:
 *   1. dry_run=true     — server validates & reports the planned creates
 *   2. dry_run=false    — actually create the rows (requires confirm)
 *
 * Both steps go through the same POST /api/registrations/{id}/convert
 * endpoint; the modal toggles `dry_run` and `confirm` in the body.
 *
 * The modal does NOT itself materialise anything — it just collects
 * intent and renders the result.  All side effects live server-side.
 */

import { useEffect, useMemo, useState } from "react";
import {
  X, Loader2, CheckCircle2, AlertTriangle, AlertCircle, Building2, User,
  Package, MapPin, FileText, Eye, Rocket, Info,
} from "lucide-react";
import { RegistrationAdminAPI } from "@/api/registrations";
import { apiFetch } from "@/api/client";

// ── Helpers ────────────────────────────────────────────────────────

/** Slugify a free-text name into a candidate tenant_id.
 *  Mirrors the server-side normalisation enough for the dry run to
 *  succeed on first try.  Hyphens, lowercase, no leading/trailing dash. */
function defaultSlug(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

const INPUT =
  "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500 disabled:bg-gray-50 disabled:text-gray-500";
const LABEL = "block text-[11px] font-semibold text-gray-600 uppercase tracking-wide mb-1";


// ── Section components ─────────────────────────────────────────────

function ChoiceTabs({ value, onChange, options }) {
  return (
    <div className="flex gap-2 mb-3">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`flex-1 px-3 py-2 text-sm rounded-lg border transition-colors ${
            value === opt.value
              ? "bg-red-50 text-red-700 border-red-300 font-medium"
              : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function TenantSection({ reg, form, setForm, tenants, tenantsLoading, isSuperAdmin }) {
  const handleChoice = (val) => {
    setForm((f) => ({
      ...f,
      tenant_choice: val,
      // Reset companion fields on choice flip so a previous selection
      // doesn't leak into the new branch's body.
      existing_tenant_id: val === "attach_existing" ? f.existing_tenant_id : "",
      new_tenant_id:
        val === "create_new"
          ? f.new_tenant_id || defaultSlug(reg.customer_name)
          : "",
      new_tenant_name:
        val === "create_new" ? f.new_tenant_name || reg.customer_name || "" : "",
    }));
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
        <Building2 className="w-4 h-4 text-red-600" /> Tenant
      </h3>
      <ChoiceTabs
        value={form.tenant_choice}
        onChange={handleChoice}
        options={[
          { value: "create_new", label: "Create new tenant" },
          { value: "attach_existing", label: "Attach to existing tenant" },
        ]}
      />

      {form.tenant_choice === "create_new" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={LABEL}>Tenant slug (url-safe)</label>
            <input
              type="text"
              value={form.new_tenant_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, new_tenant_id: defaultSlug(e.target.value) }))
              }
              placeholder="acme-property-mgmt"
              className={INPUT}
            />
          </div>
          <div>
            <label className={LABEL}>Display name</label>
            <input
              type="text"
              value={form.new_tenant_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, new_tenant_name: e.target.value }))
              }
              placeholder={reg.customer_name || "Acme Property Mgmt"}
              className={INPUT}
            />
          </div>
        </div>
      ) : (
        <div>
          <label className={LABEL}>Existing tenant</label>
          {isSuperAdmin && tenants.length > 0 ? (
            <select
              value={form.existing_tenant_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, existing_tenant_id: e.target.value }))
              }
              className={INPUT}
            >
              <option value="">— Select a tenant —</option>
              {tenants.map((t) => (
                <option key={t.tenant_id} value={t.tenant_id}>
                  {t.name} ({t.tenant_id})
                </option>
              ))}
            </select>
          ) : (
            <>
              <input
                type="text"
                value={form.existing_tenant_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, existing_tenant_id: e.target.value }))
                }
                placeholder="acme-property-mgmt"
                className={INPUT}
              />
              {tenantsLoading && (
                <p className="mt-1 text-[11px] text-gray-500 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Loading tenants…
                </p>
              )}
              {!tenantsLoading && !isSuperAdmin && (
                <p className="mt-1 text-[11px] text-gray-500">
                  Type the tenant slug exactly — full list is SuperAdmin-only.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function CustomerSection({ reg, form, setForm }) {
  const handleChoice = (val) => {
    setForm((f) => ({
      ...f,
      customer_choice: val,
      existing_customer_id: val === "attach_existing" ? f.existing_customer_id : "",
    }));
  };

  // Detect the production bug from staging: customer_name matches one
  // of the location labels.  In the Integrity case Cindy typed
  // "Tiffany Gardens East" as the company name, then re-listed it
  // as a location — so the wizard's customer_name became the same
  // string as a location's location_label.  Warn the operator before
  // they materialise the wrong account.
  const collidesWithLocation = (reg.locations || []).some((l) => {
    const name = (reg.customer_name || "").trim().toLowerCase();
    const loc = (l.location_label || "").trim().toLowerCase();
    return name && loc && name === loc;
  });

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
        <User className="w-4 h-4 text-red-600" /> Customer
      </h3>
      <p className="text-[11px] text-gray-500 mb-2">
        The Customer is the management company or ownership group — the
        top-level account. Individual buildings become Sites below.
      </p>
      <ChoiceTabs
        value={form.customer_choice}
        onChange={handleChoice}
        options={[
          { value: "create_new", label: "Create new customer" },
          { value: "attach_existing", label: "Attach to existing customer" },
        ]}
      />

      {collidesWithLocation && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 mb-2 text-xs text-amber-800 flex items-start gap-2">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <div>
            <strong>This customer name matches a location.</strong> "
            {reg.customer_name}" appears as both the company name and a
            building/property. Double-check the registration record before
            converting — the customer should be the management company
            (e.g. "Integrity Property Management"), not an individual
            building. You can edit the customer name from the reviewer
            panel without leaving this page.
          </div>
        </div>
      )}

      {form.customer_choice === "create_new" ? (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm text-gray-700 space-y-1">
          <p>
            We'll create a customer from this registration's data:
          </p>
          <ul className="ml-4 list-disc text-xs text-gray-600">
            <li>
              <span className="font-medium text-gray-800">Name:</span>{" "}
              {reg.customer_name || <em className="text-gray-400">missing — registration needs a customer name</em>}
            </li>
            <li>
              <span className="font-medium text-gray-800">Billing email:</span>{" "}
              {reg.billing_email || reg.submitter_email || <em className="text-gray-400">none on file</em>}
            </li>
            <li>
              <span className="font-medium text-gray-800">Phone:</span>{" "}
              {reg.poc_phone || reg.submitter_phone || <em className="text-gray-400">none on file</em>}
            </li>
          </ul>
        </div>
      ) : (
        <div>
          <label className={LABEL}>Existing customer ID</label>
          <input
            type="number"
            min="1"
            value={form.existing_customer_id}
            onChange={(e) =>
              setForm((f) => ({ ...f, existing_customer_id: e.target.value }))
            }
            placeholder="e.g. 42"
            className={INPUT}
          />
          <p className="mt-1 text-[11px] text-gray-500">
            Enter the customer's numeric ID. The customer must belong to the resolved tenant.
          </p>
        </div>
      )}
    </div>
  );
}

function SubscriptionSection({ reg, form, setForm }) {
  const hasPlan = !!(reg.selected_plan_code && reg.selected_plan_code.trim());

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
        <Package className="w-4 h-4 text-red-600" /> Subscription
      </h3>
      <label
        className={`flex items-start gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${
          hasPlan
            ? form.create_subscription
              ? "bg-red-50 border-red-200"
              : "bg-white border-gray-200 hover:bg-gray-50"
            : "bg-gray-50 border-gray-200 cursor-not-allowed"
        }`}
      >
        <input
          type="checkbox"
          checked={form.create_subscription && hasPlan}
          disabled={!hasPlan}
          onChange={(e) =>
            setForm((f) => ({ ...f, create_subscription: e.target.checked }))
          }
          className="mt-0.5 accent-red-600"
        />
        <div className="text-sm">
          <div className="font-medium text-gray-900">
            Also create a pending subscription
          </div>
          <div className="text-xs text-gray-500">
            {hasPlan ? (
              <>
                Plan code: <span className="font-mono">{reg.selected_plan_code}</span>{" "}
                · status will be <span className="font-semibold">pending</span> · no billing charges.
              </>
            ) : (
              <em>Disabled — this registration has no plan code selected.</em>
            )}
          </div>
        </div>
      </label>
    </div>
  );
}


// ── Result panes ───────────────────────────────────────────────────

function ResultPane({ result }) {
  if (!result) return null;
  const { dry_run, tenant, customer, sites, service_units, subscription } = result;
  return (
    <div
      className={`rounded-xl border p-4 space-y-3 ${
        dry_run
          ? "bg-blue-50 border-blue-200"
          : "bg-emerald-50 border-emerald-200"
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-semibold">
        {dry_run ? (
          <>
            <Info className="w-4 h-4 text-blue-600" />
            <span className="text-blue-800">Pre-flight passed — ready to convert</span>
          </>
        ) : (
          <>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span className="text-emerald-800">Conversion complete</span>
          </>
        )}
      </div>

      <ul className="space-y-1.5 text-xs">
        <li className="flex items-start gap-2">
          <Building2 className="w-3.5 h-3.5 text-gray-400 mt-0.5" />
          <div>
            <span className="text-gray-700">Tenant </span>
            <span className="font-mono text-gray-900">{tenant.tenant_id}</span>
            <span className="ml-1.5 text-[10px] uppercase tracking-wider text-gray-500">
              {tenant.was_created ? "created" : "attached"}
            </span>
          </div>
        </li>
        <li className="flex items-start gap-2">
          <User className="w-3.5 h-3.5 text-gray-400 mt-0.5" />
          <div>
            <span className="text-gray-700">Customer </span>
            <span className="text-gray-900">{customer.name}</span>
            <span className="ml-1.5 text-[10px] uppercase tracking-wider text-gray-500">
              {customer.was_created ? "created" : "attached"}
              {customer.id ? ` · id=${customer.id}` : ""}
            </span>
          </div>
        </li>
        <li className="flex items-start gap-2">
          <MapPin className="w-3.5 h-3.5 text-gray-400 mt-0.5" />
          <div className="flex-1">
            <span className="text-gray-700">Sites </span>
            <span className="font-semibold text-gray-900">{sites.length}</span>
            {sites.length > 0 && (
              <ul className="mt-1 ml-2 space-y-0.5">
                {sites.map((s) => (
                  <li key={s.registration_location_id} className="text-gray-600">
                    <span className="font-mono">{s.site_id}</span>
                    <span className="text-gray-400"> — {s.location_label}</span>
                    <span className="ml-1 text-[10px] uppercase tracking-wider text-gray-500">
                      {s.was_created ? "created" : "attached"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
        <li className="flex items-start gap-2">
          <FileText className="w-3.5 h-3.5 text-gray-400 mt-0.5" />
          <div>
            <span className="text-gray-700">Service units </span>
            <span className="font-semibold text-gray-900">{service_units.length}</span>
            <span className="ml-1.5 text-[10px] text-gray-500">
              {service_units.filter((u) => u.was_created).length} new
            </span>
          </div>
        </li>
        {subscription && (
          <li className="flex items-start gap-2">
            <Package className="w-3.5 h-3.5 text-gray-400 mt-0.5" />
            <div>
              <span className="text-gray-700">Subscription </span>
              <span className="font-mono text-gray-900">{subscription.plan_name}</span>
              <span className="ml-1.5 text-[10px] uppercase tracking-wider text-gray-500">
                {subscription.was_created ? "created" : "attached"} · {subscription.status}
              </span>
            </div>
          </li>
        )}
      </ul>

      {dry_run && (
        <p className="text-[11px] text-blue-800 bg-blue-100 rounded px-2 py-1.5">
          Nothing has been written yet. Click <strong>Convert</strong> below to commit.
        </p>
      )}
    </div>
  );
}

function ErrorPane({ error }) {
  if (!error) return null;
  const isNetworkError = !!error.networkError;
  const stage = error.body?.detail?.stage;
  const nextSteps = error.body?.detail?.next_steps;
  const httpStatus = error.status;
  const requestId = error.requestId;

  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-red-800 flex-wrap">
        <AlertCircle className="w-4 h-4" />
        {isNetworkError ? "No response from server" : "Conversion blocked"}
        {httpStatus && (
          <span className="text-[10px] uppercase tracking-wider bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
            HTTP {httpStatus}
          </span>
        )}
        {stage && (
          <span className="text-[10px] uppercase tracking-wider bg-red-100 text-red-700 px-1.5 py-0.5 rounded">
            stage: {stage}
          </span>
        )}
      </div>
      <p className="text-sm text-red-700">{error.message || "Unexpected error."}</p>
      {nextSteps && (
        <p className="text-xs text-red-700">
          <strong>Next steps:</strong> {nextSteps}
        </p>
      )}
      {isNetworkError && (
        <p className="text-xs text-red-700">
          The server didn't return a response. This can mean the
          request timed out (e.g. the convert took longer than the load
          balancer's window), the API container restarted mid-request,
          or the connection was dropped. Wait a moment and retry; if
          the issue persists, check the server logs for the failing
          request.
        </p>
      )}
      {requestId && (
        <p className="text-[11px] font-mono text-red-600 break-all">
          Request ID: {requestId}
        </p>
      )}
    </div>
  );
}


// ── Main modal ─────────────────────────────────────────────────────

export default function ConvertRegistrationModal({
  reg,
  isSuperAdmin,
  onClose,
  onConverted,
}) {
  // Form state — the modal mirrors the backend RegistrationConvertRequest.
  // We default to the most common reviewer choice (create new tenant +
  // customer) and prefill from the registration's data.
  const [form, setForm] = useState(() => ({
    tenant_choice: "create_new",
    existing_tenant_id: "",
    new_tenant_id: defaultSlug(reg.customer_name),
    new_tenant_name: reg.customer_name || "",
    customer_choice: "create_new",
    existing_customer_id: "",
    create_subscription: !!reg.selected_plan_code,
  }));

  const [tenants, setTenants] = useState([]);
  const [tenantsLoading, setTenantsLoading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [converting, setConverting] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);
  const [finalResult, setFinalResult] = useState(null);
  const [error, setError] = useState(null);

  // Pre-load the tenant list for SuperAdmin's attach-existing dropdown.
  useEffect(() => {
    if (!isSuperAdmin) return;
    setTenantsLoading(true);
    apiFetch("/admin/tenants")
      .then((data) => setTenants(Array.isArray(data) ? data : []))
      .catch(() => setTenants([]))
      .finally(() => setTenantsLoading(false));
  }, [isSuperAdmin]);

  // Build the request body shared by preview + real run.  Empty
  // strings get normalised to null so the schema validator doesn't
  // misinterpret "" as a present-but-empty value.
  const buildBody = (overrides = {}) => {
    const norm = (v) => (v === "" || v == null ? null : v);
    const body = {
      tenant_choice: form.tenant_choice,
      existing_tenant_id: norm(form.existing_tenant_id),
      new_tenant_id: norm(form.new_tenant_id),
      new_tenant_name: norm(form.new_tenant_name),
      customer_choice: form.customer_choice,
      existing_customer_id:
        form.existing_customer_id === "" || form.existing_customer_id == null
          ? null
          : Number(form.existing_customer_id),
      create_subscription: !!form.create_subscription,
      dry_run: false,
      confirm: false,
      ...overrides,
    };
    return body;
  };

  const localValid = useMemo(() => {
    if (form.tenant_choice === "attach_existing" && !form.existing_tenant_id) return false;
    if (form.tenant_choice === "create_new" && (!form.new_tenant_id || !form.new_tenant_name)) return false;
    if (form.customer_choice === "attach_existing" && !form.existing_customer_id) return false;
    return true;
  }, [form]);

  const handlePreview = async () => {
    setError(null);
    setPreviewResult(null);
    setFinalResult(null);
    setPreviewing(true);
    try {
      const result = await RegistrationAdminAPI.convert(
        reg.registration_id,
        buildBody({ dry_run: true, confirm: false }),
      );
      setPreviewResult(result);
    } catch (err) {
      setError(err);
    } finally {
      setPreviewing(false);
    }
  };

  const handleConvert = async () => {
    setError(null);
    setConverting(true);
    try {
      const result = await RegistrationAdminAPI.convert(
        reg.registration_id,
        buildBody({ dry_run: false, confirm: true }),
      );
      setFinalResult(result);
      // Hand the result up so the page can refresh + show the linkage
      // card.  Caller decides when (if ever) to close the modal.
      onConverted?.(result);
    } catch (err) {
      setError(err);
    } finally {
      setConverting(false);
    }
  };

  const busy = previewing || converting;
  const done = !!finalResult;

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={busy ? undefined : onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Rocket className="w-5 h-5 text-red-600" />
            <h2 className="text-base font-semibold text-gray-900">
              Convert to Production
            </h2>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 overflow-y-auto flex-1 space-y-5">
          {!done && (
            <div className="text-xs text-gray-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 text-amber-600" />
              <div>
                Conversion creates a tenant, customer, sites, and service units.{" "}
                It does <strong>not</strong> create devices, SIMs, lines, users,
                or trigger any external (T-Mobile, Field Nation, billing, E911)
                automation.
              </div>
            </div>
          )}

          {!done && <TenantSection reg={reg} form={form} setForm={setForm} tenants={tenants} tenantsLoading={tenantsLoading} isSuperAdmin={isSuperAdmin} />}
          {!done && <CustomerSection reg={reg} form={form} setForm={setForm} />}
          {!done && <SubscriptionSection reg={reg} form={form} setForm={setForm} />}

          {previewResult && !finalResult && <ResultPane result={previewResult} />}
          {finalResult && <ResultPane result={finalResult} />}
          {error && <ErrorPane error={error} />}
        </div>

        <div className="flex items-center justify-between gap-3 p-4 border-t border-gray-200 bg-gray-50">
          {done ? (
            <>
              <span className="text-xs text-gray-500">
                Production rows are now in place. The registration's status was{" "}
                <strong>not</strong> changed — advance it separately when you're ready.
              </span>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg"
              >
                Close
              </button>
            </>
          ) : (
            <>
              <button
                onClick={onClose}
                disabled={busy}
                className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50"
              >
                Cancel
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={handlePreview}
                  disabled={!localValid || busy}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium border border-gray-300 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
                >
                  {previewing ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Eye className="w-3.5 h-3.5" />
                  )}
                  Preview (Dry Run)
                </button>
                <button
                  onClick={handleConvert}
                  disabled={!localValid || busy}
                  title={
                    !previewResult
                      ? "Tip: run a dry-run preview first to surface validation problems before the real write."
                      : "Run the real conversion."
                  }
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                >
                  {converting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Rocket className="w-3.5 h-3.5" />
                  )}
                  Convert
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
