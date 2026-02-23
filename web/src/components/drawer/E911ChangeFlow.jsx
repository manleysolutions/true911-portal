import { useState } from "react";
import { MapPin, CheckCircle, AlertTriangle, Loader2, ChevronRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { E911ChangeLog } from "@/api/entities";
import { updateE911 } from "../actions";
import { toast } from "sonner";
import { uid } from "../actions";

const STEPS = ["view", "form", "confirm", "result"];

export default function E911ChangeFlow({ site, onClose, onSiteUpdated }) {
  const { user } = useAuth();
  const [step, setStep] = useState("form");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const [form, setForm] = useState({
    street: site.e911_street || "",
    city: site.e911_city || "",
    state: site.e911_state || "",
    zip: site.e911_zip || "",
    reason: "",
  });

  const handleSubmit = async () => {
    setLoading(true);
    const correlation_id = uid("E911");

    // Write to E911ChangeLog first
    await E911ChangeLog.create({
      log_id: uid("LOG"),
      site_id: site.site_id,
      tenant_id: site.tenant_id,
      requested_by: user.email,
      requester_name: user.name,
      requested_at: new Date().toISOString(),
      old_street: site.e911_street,
      old_city: site.e911_city,
      old_state: site.e911_state,
      old_zip: site.e911_zip,
      new_street: form.street,
      new_city: form.city,
      new_state: form.state,
      new_zip: form.zip,
      reason: form.reason,
      status: "applied",
      applied_at: new Date().toISOString(),
      correlation_id,
    });

    // Apply the change
    const r = await updateE911(user, site, { street: form.street, city: form.city, state: form.state, zip: form.zip });
    setLoading(false);
    setResult({ success: r.success, correlation_id });
    setStep("result");
    onSiteUpdated?.();
  };

  if (step === "form") {
    return (
      <div className="space-y-3">
        <div className="bg-gray-50 rounded-lg p-3 mb-2">
          <div className="text-[10px] font-semibold text-gray-400 uppercase mb-1">Current E911 (Read-only)</div>
          <div className="text-xs text-gray-700 font-medium">{site.e911_street || "—"}</div>
          <div className="text-xs text-gray-500">{site.e911_city}, {site.e911_state} {site.e911_zip}</div>
        </div>

        <div className="text-[10px] font-semibold text-gray-400 uppercase">Proposed Change</div>

        {[
          { key: "street", label: "Street Address", placeholder: "123 Main St" },
          { key: "city", label: "City", placeholder: "New York" },
          { key: "state", label: "State", placeholder: "NY" },
          { key: "zip", label: "ZIP Code", placeholder: "10001" },
        ].map(({ key, label, placeholder }) => (
          <div key={key}>
            <label className="block text-[10px] font-medium text-gray-600 mb-1">{label}</label>
            <input
              value={form[key]}
              onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
              placeholder={placeholder}
              className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-purple-500"
            />
          </div>
        ))}

        <div>
          <label className="block text-[10px] font-medium text-gray-600 mb-1">Reason for Change *</label>
          <textarea
            value={form.reason}
            onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
            placeholder="e.g. Physical relocation, address correction, AHJ requirement..."
            rows={2}
            className="w-full px-3 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-purple-500 resize-none"
          />
        </div>

        <div className="flex gap-2 pt-1">
          <button
            onClick={onClose}
            className="flex-1 px-3 py-2 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 font-medium"
          >
            Cancel
          </button>
          <button
            onClick={() => setStep("confirm")}
            disabled={!form.street || !form.reason}
            className="flex-1 px-3 py-2 text-xs bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1"
          >
            Review <ChevronRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    );
  }

  if (step === "confirm") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-semibold text-gray-800">Confirm E911 Change</span>
        </div>

        <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-xs text-amber-800 leading-relaxed">
          This change will update the E911 dispatch address for <strong>{site.site_name}</strong>. All changes are logged and auditable.
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-red-50 rounded-lg p-2.5">
            <div className="text-[10px] font-bold text-red-500 mb-1">BEFORE</div>
            <div className="text-gray-700">{site.e911_street}</div>
            <div className="text-gray-500">{site.e911_city}, {site.e911_state} {site.e911_zip}</div>
          </div>
          <div className="bg-emerald-50 rounded-lg p-2.5">
            <div className="text-[10px] font-bold text-emerald-600 mb-1">AFTER</div>
            <div className="text-gray-700">{form.street}</div>
            <div className="text-gray-500">{form.city}, {form.state} {form.zip}</div>
          </div>
        </div>

        <div className="bg-gray-50 rounded-lg p-2.5 text-xs">
          <div className="text-gray-500">Requester: <span className="font-medium text-gray-800">{user.name} ({user.role})</span></div>
          <div className="text-gray-500 mt-0.5">Reason: <span className="font-medium text-gray-800">{form.reason}</span></div>
          <div className="text-gray-500 mt-0.5">Timestamp: <span className="font-mono text-gray-700">{new Date().toISOString()}</span></div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setStep("form")}
            className="flex-1 px-3 py-2 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 font-medium"
          >
            Back
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex-1 px-3 py-2 text-xs bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-semibold disabled:opacity-60 flex items-center justify-center gap-1"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            {loading ? "Applying..." : "Apply Change"}
          </button>
        </div>
      </div>
    );
  }

  if (step === "result") {
    return (
      <div className="space-y-4 text-center">
        <div className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto ${result?.success ? "bg-emerald-100" : "bg-red-100"}`}>
          {result?.success
            ? <CheckCircle className="w-6 h-6 text-emerald-600" />
            : <AlertTriangle className="w-6 h-6 text-red-600" />
          }
        </div>
        <div>
          <div className="text-sm font-semibold text-gray-900">{result?.success ? "E911 Address Updated" : "Update Failed"}</div>
          <div className="text-xs text-gray-500 mt-1">Status: <span className={`font-semibold ${result?.success ? "text-emerald-600" : "text-red-600"}`}>{result?.success ? "Applied" : "Failed"}</span></div>
          <div className="text-[10px] text-gray-400 mt-1 font-mono">{result?.correlation_id}</div>
        </div>
        <button
          onClick={onClose}
          className="w-full px-3 py-2 text-xs bg-gray-900 text-white rounded-lg hover:bg-gray-800 font-semibold"
        >
          Done
        </button>
      </div>
    );
  }

  return null;
}