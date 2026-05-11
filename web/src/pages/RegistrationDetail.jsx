/**
 * Registration detail / review page (Phase R3).
 *
 * Authenticated.  Gated by VIEW_REGISTRATIONS for the read shape and
 * MANAGE_REGISTRATIONS for any action button (transition, request
 * info, cancel, edit reviewer notes).
 *
 * No conversion logic on this page — converting a registration into
 * production rows lives in Phase R4 behind the CONVERT_REGISTRATIONS
 * permission.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  ArrowLeft, ClipboardList, Building2, User, MapPin, Phone, Calendar, CreditCard,
  AlertCircle, Clock, Loader2, Save, MessageSquare, X,
  Hash, ShieldCheck,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { RegistrationAdminAPI } from "@/api/registrations";
import { toast } from "sonner";

// ── Status / transition presentation ────────────────────────────────

const STATUS_LABELS = {
  draft: "Draft",
  submitted: "Submitted",
  internal_review: "In Review",
  pending_customer_info: "Awaiting Customer",
  pending_equipment_assignment: "Equipment Pending",
  pending_sim_assignment: "SIM Pending",
  pending_installer_schedule: "Scheduling",
  scheduled: "Scheduled",
  installed: "Installed",
  qa_review: "QA Review",
  ready_for_activation: "Ready For Activation",
  active: "Active",
  cancelled: "Cancelled",
};

const STATUS_TONE = {
  draft: "bg-slate-100 text-slate-700 border-slate-200",
  submitted: "bg-blue-50 text-blue-700 border-blue-200",
  internal_review: "bg-indigo-50 text-indigo-700 border-indigo-200",
  pending_customer_info: "bg-amber-50 text-amber-700 border-amber-200",
  pending_equipment_assignment: "bg-violet-50 text-violet-700 border-violet-200",
  pending_sim_assignment: "bg-violet-50 text-violet-700 border-violet-200",
  pending_installer_schedule: "bg-violet-50 text-violet-700 border-violet-200",
  scheduled: "bg-cyan-50 text-cyan-700 border-cyan-200",
  installed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  qa_review: "bg-emerald-50 text-emerald-700 border-emerald-200",
  ready_for_activation: "bg-emerald-50 text-emerald-700 border-emerald-200",
  active: "bg-emerald-100 text-emerald-800 border-emerald-300",
  cancelled: "bg-red-50 text-red-700 border-red-200",
};

// Action buttons exposed on the detail page.  Each entry maps to a
// transition target plus the friendly button label and a short help
// hint shown on hover.  Order matters — the row renders in this
// sequence.
const ACTION_BUTTONS = [
  { to: "internal_review", label: "Move to Review", hint: "Begin internal review." },
  { to: "pending_equipment_assignment", label: "Equipment Assignment", hint: "Mark as awaiting equipment." },
  { to: "pending_sim_assignment", label: "SIM Assignment", hint: "Mark as awaiting SIMs." },
  { to: "pending_installer_schedule", label: "Schedule Installer", hint: "Move to installer scheduling." },
  { to: "scheduled", label: "Mark Scheduled", hint: "Installer confirmed." },
  { to: "installed", label: "Mark Installed", hint: "Field work complete." },
  { to: "qa_review", label: "QA Review", hint: "Begin quality review." },
  { to: "ready_for_activation", label: "Ready For Activation", hint: "Cleared QA — ready to go live." },
];

// Mirror of the backend state machine.  Kept client-side so we can
// pre-disable buttons that the server would reject anyway — but the
// server remains the source of truth (a 409 is always handled).
const ALLOWED_NEXT = {
  draft: ["submitted", "cancelled"],
  submitted: ["internal_review", "cancelled"],
  internal_review: ["pending_customer_info", "pending_equipment_assignment", "cancelled"],
  pending_customer_info: ["internal_review", "cancelled"],
  pending_equipment_assignment: ["pending_sim_assignment", "cancelled"],
  pending_sim_assignment: ["pending_installer_schedule", "cancelled"],
  pending_installer_schedule: ["scheduled", "cancelled"],
  scheduled: ["installed", "cancelled"],
  installed: ["qa_review", "cancelled"],
  qa_review: ["ready_for_activation", "pending_equipment_assignment", "cancelled"],
  ready_for_activation: ["active", "cancelled"],
  active: [],
  cancelled: [],
};


function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || STATUS_TONE.draft;
  const label = STATUS_LABELS[status] || status;
  return (
    <span className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full border ${tone}`}>
      {label}
    </span>
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch { return "—"; }
}


// ── Modals ──────────────────────────────────────────────────────────

function PromptModal({ title, label, placeholder, helper, confirmLabel = "Submit", confirmTone = "red", onClose, onConfirm }) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleConfirm = async () => {
    if (!value.trim()) return;
    setSubmitting(true);
    try {
      await onConfirm(value.trim());
      onClose();
    } catch (err) {
      toast.error(err?.message || "Action failed");
      setSubmitting(false);
    }
  };

  const tone = confirmTone === "red"
    ? "bg-red-600 hover:bg-red-700"
    : "bg-blue-600 hover:bg-blue-700";

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-gray-900">{title}</h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600"><X className="w-4 h-4" /></button>
        </div>
        <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">{label}</label>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          rows={4}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500 resize-none"
        />
        {helper && <p className="text-[11px] text-gray-500 mt-1">{helper}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900">Cancel</button>
          <button
            onClick={handleConfirm}
            disabled={!value.trim() || submitting}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-white text-sm font-semibold rounded-lg disabled:opacity-50 ${tone}`}
          >
            {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />} {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}


// ── Page ────────────────────────────────────────────────────────────

export default function RegistrationDetail() {
  const [params] = useSearchParams();
  const registrationId = params.get("id");
  const { can } = useAuth();
  const canView = can("VIEW_REGISTRATIONS");
  const canManage = can("MANAGE_REGISTRATIONS");

  const [reg, setReg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showRequestInfo, setShowRequestInfo] = useState(false);
  const [showCancel, setShowCancel] = useState(false);

  const reload = useCallback(async () => {
    if (!registrationId) return;
    setLoading(true);
    setError("");
    try {
      const data = await RegistrationAdminAPI.get(registrationId);
      setReg(data);
    } catch (err) {
      const status = err?.status;
      if (status === 404) setError("Registration not found.");
      else if (status === 403) setError("You do not have permission to view this registration.");
      else setError(err?.message || "Failed to load registration.");
      setReg(null);
    } finally {
      setLoading(false);
    }
  }, [registrationId]);

  useEffect(() => {
    if (canView) reload();
  }, [reload, canView]);

  const handleTransition = async (toStatus, note) => {
    try {
      const updated = await RegistrationAdminAPI.transition(registrationId, toStatus, note);
      setReg(updated);
      toast.success(`Moved to ${STATUS_LABELS[toStatus] || toStatus}`);
    } catch (err) {
      toast.error(err?.message || "Transition failed");
    }
  };

  const handleRequestInfo = async (message) => {
    const updated = await RegistrationAdminAPI.requestInfo(registrationId, message);
    setReg(updated);
    toast.success("Marked as awaiting customer information");
  };

  const handleCancel = async (reason) => {
    const updated = await RegistrationAdminAPI.cancel(registrationId, reason);
    setReg(updated);
    toast.success("Registration cancelled");
  };

  if (!canView) {
    return (
      <PageWrapper>
        <div className="p-6 text-sm text-gray-500">
          You do not have permission to view registrations.
        </div>
      </PageWrapper>
    );
  }

  if (!registrationId) {
    return (
      <PageWrapper>
        <div className="p-6">
          <Link to={createPageUrl("Registrations")} className="text-sm text-red-600 hover:text-red-700 inline-flex items-center gap-1">
            <ArrowLeft className="w-3.5 h-3.5" /> Back to list
          </Link>
          <p className="mt-4 text-sm text-gray-500">No registration reference supplied.</p>
        </div>
      </PageWrapper>
    );
  }

  if (loading) {
    return (
      <PageWrapper>
        <div className="p-6 text-sm text-gray-400 flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      </PageWrapper>
    );
  }

  if (error || !reg) {
    return (
      <PageWrapper>
        <div className="max-w-2xl mx-auto p-6">
          <Link to={createPageUrl("Registrations")} className="text-sm text-red-600 hover:text-red-700 inline-flex items-center gap-1 mb-4">
            <ArrowLeft className="w-3.5 h-3.5" /> Back to list
          </Link>
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" /> {error || "Registration not found."}
          </div>
        </div>
      </PageWrapper>
    );
  }

  const allowedNext = ALLOWED_NEXT[reg.status] || [];
  const totalUnits = (reg.locations || []).reduce((acc, l) => acc + (l.service_units?.length || 0), 0);

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-5xl mx-auto p-6 space-y-5">
          {/* Header */}
          <div>
            <Link to={createPageUrl("Registrations")} className="text-xs text-red-600 hover:text-red-700 inline-flex items-center gap-1 mb-3">
              <ArrowLeft className="w-3 h-3" /> Back to registrations
            </Link>
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-12 h-12 bg-red-600 rounded-xl flex items-center justify-center flex-shrink-0">
                  <ClipboardList className="w-6 h-6 text-white" />
                </div>
                <div className="min-w-0">
                  <h1 className="text-xl font-bold text-gray-900 truncate">
                    {reg.customer_name || "Untitled Registration"}
                  </h1>
                  <p className="text-xs text-gray-500 font-mono">{reg.registration_id}</p>
                </div>
              </div>
              <StatusBadge status={reg.status} />
            </div>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Locations" value={reg.locations?.length || 0} />
            <Stat label="Phones" value={totalUnits} />
            <Stat label="Plan" value={(reg.selected_plan_code || "—").replace(/_/g, " ")} />
            <Stat label="Submitted" value={reg.submitted_at ? formatDate(reg.submitted_at) : "—"} />
          </div>

          {/* Action bar */}
          {canManage && reg.status !== "active" && reg.status !== "cancelled" && (
            <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-2">
              <div className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Reviewer Actions</div>
              <div className="flex flex-wrap gap-2">
                {ACTION_BUTTONS.map((a) => {
                  const enabled = allowedNext.includes(a.to);
                  return (
                    <button
                      key={a.to}
                      onClick={() => enabled && handleTransition(a.to)}
                      disabled={!enabled}
                      title={enabled ? a.hint : `Cannot move to ${STATUS_LABELS[a.to]} from ${STATUS_LABELS[reg.status]}.`}
                      className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                        enabled
                          ? "bg-white text-gray-700 border-gray-200 hover:bg-gray-50 hover:border-gray-300"
                          : "bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed"
                      }`}
                    >
                      {a.label}
                    </button>
                  );
                })}
                <button
                  onClick={() => setShowRequestInfo(true)}
                  disabled={!allowedNext.includes("pending_customer_info")}
                  title={
                    allowedNext.includes("pending_customer_info")
                      ? "Ask the customer for more info."
                      : `Cannot request info from ${STATUS_LABELS[reg.status]}.`
                  }
                  className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                    allowedNext.includes("pending_customer_info")
                      ? "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"
                      : "bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed"
                  }`}
                >
                  Request More Info
                </button>
                <button
                  onClick={() => setShowCancel(true)}
                  className="text-xs font-medium px-3 py-1.5 rounded-lg border border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
                >
                  Cancel Registration
                </button>
              </div>
              <p className="text-[11px] text-gray-400">
                Conversion to a customer / sites / service units is a separate step (Phase R4) and not yet enabled.
              </p>
            </div>
          )}

          {/* Two-column body */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left two-thirds — record content */}
            <div className="lg:col-span-2 space-y-4">
              <Card icon={Building2} title="Customer">
                <DetailRow label="Company" value={reg.customer_name} />
                <DetailRow label="Legal Name" value={reg.customer_legal_name} />
                <DetailRow label="Submitted By" value={reg.submitter_name} />
                <DetailRow label="Email" value={reg.submitter_email} />
                <DetailRow label="Phone" value={reg.submitter_phone} />
              </Card>

              <Card icon={User} title="Main Contact">
                <DetailRow label="Name" value={reg.poc_name} />
                <DetailRow label="Phone" value={reg.poc_phone} />
                <DetailRow label="Email" value={reg.poc_email} />
                <DetailRow label="Role" value={reg.poc_role} />
              </Card>

              {reg.use_case_summary && (
                <Card icon={MessageSquare} title="Use Case">
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{reg.use_case_summary}</p>
                </Card>
              )}

              {(reg.locations || []).map((loc) => (
                <Card key={loc.id} icon={MapPin} title={loc.location_label}>
                  <p className="text-sm text-gray-700">
                    {[loc.street, loc.city, loc.state, loc.zip].filter(Boolean).join(", ") || <em className="text-gray-400">Address not provided</em>}
                  </p>
                  {loc.dispatchable_description && (
                    <p className="text-xs text-gray-600 mt-2">
                      <strong className="text-gray-800">Dispatch detail:</strong> {loc.dispatchable_description}
                    </p>
                  )}
                  {loc.access_notes && (
                    <p className="text-xs text-gray-600 mt-1">
                      <strong className="text-gray-800">Access:</strong> {loc.access_notes}
                    </p>
                  )}
                  {(loc.service_units || []).length > 0 && (
                    <div className="mt-3 border-t border-gray-100 pt-3">
                      <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Service Units</div>
                      <ul className="space-y-1.5">
                        {loc.service_units.map((u) => (
                          <li key={u.id} className="text-sm text-gray-700 flex items-center flex-wrap gap-2">
                            <Phone className="w-3 h-3 text-gray-400" />
                            <span className="font-medium">{u.unit_label}</span>
                            <span className="text-[11px] text-gray-500">{u.unit_type}</span>
                            {u.phone_number_existing && (
                              <span className="inline-flex items-center gap-1 text-[11px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">
                                <Hash className="w-2.5 h-2.5" />{u.phone_number_existing}
                              </span>
                            )}
                            {u.hardware_model_request && (
                              <span className="text-[11px] text-gray-500">{u.hardware_model_request}</span>
                            )}
                            {u.carrier_request && (
                              <span className="text-[11px] text-gray-500">/ {u.carrier_request}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Card>
              ))}

              {(reg.preferred_install_window_start || reg.preferred_install_window_end || reg.installer_notes) && (
                <Card icon={Calendar} title="Scheduling Preference">
                  <DetailRow label="Earliest" value={reg.preferred_install_window_start ? formatDate(reg.preferred_install_window_start) : null} />
                  <DetailRow label="Latest" value={reg.preferred_install_window_end ? formatDate(reg.preferred_install_window_end) : null} />
                  {reg.installer_notes && (
                    <p className="text-xs text-gray-600 mt-2 whitespace-pre-wrap">{reg.installer_notes}</p>
                  )}
                </Card>
              )}

              <Card icon={CreditCard} title="Billing & Support">
                <DetailRow label="Plan" value={reg.selected_plan_code} />
                <DetailRow label="Estimated Lines" value={reg.plan_quantity_estimate} />
                <DetailRow label="Billing Method" value={reg.billing_method} />
                <DetailRow label="Billing Email" value={reg.billing_email} />
                <DetailRow
                  label="Billing Address"
                  value={[reg.billing_address_street, reg.billing_address_city, reg.billing_address_state, reg.billing_address_zip].filter(Boolean).join(", ")}
                />
                {reg.support_preference_json && (
                  <div className="mt-2 text-xs text-gray-600">
                    <strong className="text-gray-800">Support prefs:</strong>{" "}
                    {(reg.support_preference_json.channels || []).join(", ") || <span className="text-gray-400">not set</span>}
                    {reg.support_preference_json.after_hours_contact && (
                      <span> · after hours: {reg.support_preference_json.after_hours_contact}</span>
                    )}
                  </div>
                )}
              </Card>
            </div>

            {/* Right third — reviewer panel + timeline */}
            <div className="space-y-4">
              <ReviewerPanel reg={reg} canManage={canManage} onSaved={(updated) => setReg(updated)} />
              <TimelineCard events={reg.status_events || []} />
            </div>
          </div>
        </div>
      </div>

      {showRequestInfo && (
        <PromptModal
          title="Request More Info"
          label="What do you need from the customer?"
          placeholder="e.g. Please confirm the gate code for after-hours access."
          helper="Recorded on the registration's timeline. Phase R3 does not email the customer."
          confirmLabel="Send to Customer"
          confirmTone="blue"
          onClose={() => setShowRequestInfo(false)}
          onConfirm={handleRequestInfo}
        />
      )}
      {showCancel && (
        <PromptModal
          title="Cancel Registration"
          label="Reason for cancelling"
          placeholder="e.g. Duplicate of REG-XYZ123."
          helper="Logged on the registration's timeline and stamped on the row."
          confirmLabel="Cancel Registration"
          confirmTone="red"
          onClose={() => setShowCancel(false)}
          onConfirm={handleCancel}
        />
      )}
    </PageWrapper>
  );
}


// ── Subcomponents ───────────────────────────────────────────────────

function Stat({ label, value }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3">
      <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{label}</div>
      <div className="text-lg font-bold text-gray-900 mt-0.5 truncate" title={typeof value === "string" ? value : undefined}>
        {value || "—"}
      </div>
    </div>
  );
}

function Card({ icon: Icon, title, children }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
        <Icon className="w-4 h-4 text-red-600" /> {title}
      </div>
      <div>{children}</div>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-sm">
      <span className="text-[10px] uppercase tracking-wide text-gray-500 mt-0.5">{label}</span>
      <span className="text-gray-800 text-right">
        {(value === null || value === undefined || value === "")
          ? <span className="italic text-gray-400">not set</span>
          : value}
      </span>
    </div>
  );
}

function ReviewerPanel({ reg, canManage, onSaved }) {
  const [notes, setNotes] = useState(reg.reviewer_notes || "");
  const [plan, setPlan] = useState(reg.selected_plan_code || "");
  const [quantity, setQuantity] = useState(reg.plan_quantity_estimate || "");
  const [targetTenant, setTargetTenant] = useState(reg.target_tenant_id || "");
  const [billingMethod, setBillingMethod] = useState(reg.billing_method || "");
  const [saving, setSaving] = useState(false);

  // Reset local form state whenever the parent loads a fresh record
  // (e.g. after a status transition refresh).
  useEffect(() => {
    setNotes(reg.reviewer_notes || "");
    setPlan(reg.selected_plan_code || "");
    setQuantity(reg.plan_quantity_estimate || "");
    setTargetTenant(reg.target_tenant_id || "");
    setBillingMethod(reg.billing_method || "");
  }, [reg.id, reg.reviewer_notes, reg.selected_plan_code, reg.plan_quantity_estimate, reg.target_tenant_id, reg.billing_method]);

  const dirty = useMemo(() => (
    notes !== (reg.reviewer_notes || "")
    || plan !== (reg.selected_plan_code || "")
    || String(quantity ?? "") !== String(reg.plan_quantity_estimate ?? "")
    || targetTenant !== (reg.target_tenant_id || "")
    || billingMethod !== (reg.billing_method || "")
  ), [notes, plan, quantity, targetTenant, billingMethod, reg]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        reviewer_notes: notes || null,
        selected_plan_code: plan || null,
        plan_quantity_estimate: quantity === "" ? null : Number(quantity),
        target_tenant_id: targetTenant || null,
        billing_method: billingMethod || null,
      };
      const updated = await RegistrationAdminAPI.update(reg.registration_id, payload);
      onSaved?.(updated);
      toast.success("Reviewer notes saved");
    } catch (err) {
      toast.error(err?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card icon={ShieldCheck} title="Reviewer">
      {!canManage && (
        <p className="text-[11px] text-gray-500 italic mb-2">
          View-only — your role can't edit reviewer fields.
        </p>
      )}
      <label className="block text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Reviewer Notes</label>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        disabled={!canManage}
        rows={4}
        placeholder="Internal notes about this registration…"
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500 resize-none disabled:bg-gray-50 disabled:text-gray-500"
      />

      <div className="mt-3 space-y-2.5">
        <Field
          label="Plan Code"
          value={plan}
          onChange={setPlan}
          disabled={!canManage}
          placeholder="e.g. monitoring_e911"
        />
        <Field
          label="Estimated Lines"
          value={quantity}
          onChange={setQuantity}
          disabled={!canManage}
          type="number"
        />
        <Field
          label="Target Tenant Slug"
          value={targetTenant}
          onChange={setTargetTenant}
          disabled={!canManage}
          placeholder="Picked at conversion (Phase R4)"
        />
        <Field
          label="Billing Method"
          value={billingMethod}
          onChange={setBillingMethod}
          disabled={!canManage}
          placeholder="invoice | ach | credit_card | other"
        />
      </div>

      {canManage && (
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="mt-3 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white text-sm font-semibold rounded-lg"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Save Reviewer Fields
        </button>
      )}
    </Card>
  );
}

function Field({ label, value, onChange, disabled = false, placeholder = "", type = "text" }) {
  return (
    <div>
      <label className="block text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">{label}</label>
      <input
        type={type}
        value={value === null || value === undefined ? "" : value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500 disabled:bg-gray-50 disabled:text-gray-500"
      />
    </div>
  );
}

function TimelineCard({ events }) {
  if (!events || events.length === 0) {
    return (
      <Card icon={Clock} title="Timeline">
        <p className="text-sm text-gray-400 italic">No events yet.</p>
      </Card>
    );
  }
  return (
    <Card icon={Clock} title="Timeline">
      <ol className="space-y-3">
        {events.slice().reverse().map((ev) => (
          <li key={ev.id} className="relative pl-6">
            <div className="absolute left-0 top-1.5 w-2.5 h-2.5 rounded-full bg-red-500 ring-4 ring-red-100" />
            <div className="text-xs text-gray-700 font-semibold">
              {STATUS_LABELS[ev.to_status] || ev.to_status}
              {ev.from_status && (
                <span className="text-gray-400 font-normal"> ← {STATUS_LABELS[ev.from_status] || ev.from_status}</span>
              )}
            </div>
            <div className="text-[11px] text-gray-500">
              {formatDate(ev.created_at)}
              {ev.actor_email && <> · {ev.actor_email}</>}
            </div>
            {ev.note && (
              <div className="text-xs text-gray-600 mt-1 whitespace-pre-wrap border-l-2 border-gray-200 pl-2">
                {ev.note}
              </div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}
