import { useState } from "react";
import { Deployment } from "@/api/entities";
import { useAuth } from "@/contexts/AuthContext";
import PageWrapper from "@/components/PageWrapper";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Rocket, Loader2, CheckCircle2, XCircle, Copy, Check,
  Building2, MapPin, Radio, User, ExternalLink, AlertTriangle,
} from "lucide-react";

const STEP_LABELS = {
  tenant: "Tenant",
  customer: "Customer",
  site: "Site",
  vola_connect: "VOLA Connection",
  devices: "Devices",
  user_invite: "User Invite",
  vola_validate: "VOLA Validate",
  ensure_device: "Create Device",
  bind_to_site: "Bind to Site",
  provision: "Provision",
  reboot: "Reboot",
  verify: "Verify",
};

const STEP_ORDER = ["tenant", "customer", "site", "vola_connect", "devices", "user_invite"];

function StepResult({ stepKey, value }) {
  const label = STEP_LABELS[stepKey] || stepKey;
  const isOk = value === "ok" || value === "created" || value === "already_exists" || value.startsWith("ok") || /^\d+\/\d+ succeeded$/.test(value);
  const isSkip = value.startsWith("skipped");
  return (
    <div className="flex items-center gap-2.5">
      <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
        isOk ? "bg-emerald-100" : isSkip ? "bg-gray-100" : "bg-red-100"
      }`}>
        {isOk ? <CheckCircle2 className="w-3 h-3 text-emerald-600" /> :
         isSkip ? <div className="w-1.5 h-1.5 rounded-full bg-gray-400" /> :
         <XCircle className="w-3 h-3 text-red-600" />}
      </div>
      <span className="text-xs text-gray-600 w-28">{label}</span>
      <span className={`text-xs font-mono ${isOk ? "text-emerald-700" : isSkip ? "text-gray-400" : "text-red-700"}`}>{value}</span>
    </div>
  );
}

function DeviceResult({ d }) {
  const ok = d.status === "success";
  const partial = d.status === "partial";
  const stepOrder = ["vola_validate", "ensure_device", "bind_to_site", "provision", "reboot", "verify"];
  return (
    <div className={`rounded-xl border px-4 py-3 ${ok ? "bg-emerald-50 border-emerald-200" : partial ? "bg-amber-50 border-amber-200" : "bg-red-50 border-red-200"}`}>
      <div className="flex items-center gap-2 mb-2">
        {ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <XCircle className="w-4 h-4 text-red-600" />}
        <span className="text-sm font-bold text-gray-900">{d.device_sn}</span>
        {d.device_id && <span className="text-xs text-gray-400">{d.device_id}</span>}
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ml-auto ${ok ? "bg-emerald-100 text-emerald-700" : partial ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"}`}>
          {d.status}
        </span>
      </div>
      {/* Step badges */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {stepOrder.filter(k => d.steps?.[k]).map(k => {
          const v = d.steps[k];
          const isOk = v === "ok" || v === "success";
          const isWarn = v.startsWith("not_found") || v === "mismatch" || v.startsWith("skipped");
          const label = STEP_LABELS[k] || k.replace(/_/g, " ");
          return (
            <span key={k} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${
              isOk ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
              isWarn ? "bg-amber-50 text-amber-700 border-amber-200" :
              "bg-red-50 text-red-700 border-red-200"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isOk ? "bg-emerald-500" : isWarn ? "bg-amber-500" : "bg-red-500"}`} />
              {label}
            </span>
          );
        })}
      </div>
      {/* Applied params */}
      {d.applied && Object.keys(d.applied).length > 0 && (
        <div className="text-xs text-gray-600 mb-1">
          <span className="text-gray-400">Applied:</span> {Object.entries(d.applied).map(([k, v]) => `${k.split(".").pop()}=${v}`).join(", ")}
        </div>
      )}
      {/* Verified values */}
      {d.verified_values && Object.keys(d.verified_values).length > 0 && (
        <div className="text-xs text-emerald-700 mb-1">
          <span className="text-gray-400">Verified:</span> {Object.entries(d.verified_values).map(([k, v]) => `${k.split(".").pop()}=${v}`).join(", ")}
        </div>
      )}
      {d.error && <div className="text-xs text-red-700 mt-1">{d.error}</div>}
    </div>
  );
}

function CopyField({ label, value }) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;
  const handleCopy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
      <div>
        <div className="text-[10px] text-gray-400 uppercase">{label}</div>
        <div className="text-sm font-mono text-gray-800 break-all">{value}</div>
      </div>
      <button onClick={handleCopy} className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-400 flex-shrink-0 ml-2">
        {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}


export default function ProvisionDeployment() {
  const { can } = useAuth();

  // Form
  const [customerName, setCustomerName] = useState("");
  const [siteName, setSiteName] = useState("");
  const [address, setAddress] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactName, setContactName] = useState("");
  const [deviceSns, setDeviceSns] = useState("");
  const [siteCode, setSiteCode] = useState("");
  const [carrier, setCarrier] = useState("");

  // State
  const [deploying, setDeploying] = useState(false);
  const [result, setResult] = useState(null);

  const parsedSns = deviceSns.split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
  const canDeploy = customerName.trim() && siteName.trim() && parsedSns.length > 0;

  const handleDeploy = async () => {
    setDeploying(true);
    setResult(null);
    try {
      const res = await Deployment.provision({
        customer_name: customerName.trim(),
        site_name: siteName.trim(),
        address: address.trim() || undefined,
        contact_email: contactEmail.trim() || undefined,
        contact_name: contactName.trim() || undefined,
        device_sns: parsedSns,
        site_code: siteCode.trim() || undefined,
        carrier: carrier.trim() || undefined,
      });
      setResult(res);
      if (res.status === "success") toast.success("Deployment completed successfully");
      else if (res.status === "partial") toast.warning("Deployment partially succeeded");
      else toast.error(res.error || "Deployment failed");
    } catch (err) {
      toast.error(err?.message || "Deployment failed");
      setResult({ status: "failed", error: err?.message, steps: {}, devices: [] });
    }
    setDeploying(false);
  };

  const handleReset = () => {
    setResult(null);
    setCustomerName("");
    setSiteName("");
    setAddress("");
    setContactEmail("");
    setContactName("");
    setDeviceSns("");
    setSiteCode("");
    setCarrier("");
  };

  if (!can("MANAGE_DEVICES")) {
    return (
      <PageWrapper>
        <div className="p-6 max-w-3xl mx-auto text-center py-16">
          <div className="text-sm text-gray-500">Admin permissions required.</div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Provision Deployment</h1>
          <p className="text-sm text-gray-500 mt-0.5">Zero-touch onboarding: customer + site + PR12 devices + user account in one step</p>
        </div>

        {!result ? (
          /* ── Form ── */
          <div className="space-y-5">
            {/* Customer */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
              <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
                <Building2 className="w-4 h-4 text-red-600" /> Customer
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Customer Name *</label>
                  <input value={customerName} onChange={e => setCustomerName(e.target.value)} placeholder="e.g. Test Building A" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Contact Email</label>
                  <input value={contactEmail} onChange={e => setContactEmail(e.target.value)} type="email" placeholder="operator@company.com" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Contact Name</label>
                <input value={contactName} onChange={e => setContactName(e.target.value)} placeholder="John Smith" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
              </div>
            </div>

            {/* Site */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
              <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
                <MapPin className="w-4 h-4 text-red-600" /> Site
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Site Name *</label>
                  <input value={siteName} onChange={e => setSiteName(e.target.value)} placeholder="e.g. Main Elevator" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Site Code</label>
                  <input value={siteCode} onChange={e => setSiteCode(e.target.value)} placeholder="Auto-generated if blank" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Address</label>
                <input value={address} onChange={e => setAddress(e.target.value)} placeholder="123 Main St, City, ST 12345" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
                <div className="text-[11px] text-gray-400 mt-1">Format: street, city, state zip (used for E911)</div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Carrier</label>
                <select value={carrier} onChange={e => setCarrier(e.target.value)} className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500">
                  <option value="">-- Optional --</option>
                  <option value="Verizon">Verizon</option>
                  <option value="AT&T">AT&T</option>
                  <option value="T-Mobile">T-Mobile</option>
                  <option value="Telnyx">Telnyx</option>
                </select>
              </div>
            </div>

            {/* Devices */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
              <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
                <Radio className="w-4 h-4 text-red-600" /> PR12 Devices
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Device Serial Numbers *</label>
                <textarea
                  value={deviceSns}
                  onChange={e => setDeviceSns(e.target.value)}
                  placeholder={"Enter serial numbers, one per line or comma-separated.\nExample: SN001\nSN002"}
                  rows={3}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-red-500 resize-none"
                />
                <div className="text-[11px] text-gray-400 mt-1">
                  {parsedSns.length > 0 ? `${parsedSns.length} device(s): ${parsedSns.join(", ")}` : "Scan or type device serial numbers"}
                </div>
              </div>
            </div>

            {/* Deploy button */}
            <div className="flex items-center justify-between">
              <div className="text-xs text-gray-400">
                {parsedSns.length > 0 && (
                  <span>Est. time: ~{parsedSns.length * 30}s</span>
                )}
              </div>
              <button
                onClick={handleDeploy}
                disabled={deploying || !canDeploy}
                className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white rounded-xl text-sm font-bold shadow-sm transition-colors"
              >
                {deploying ? <><Loader2 className="w-4 h-4 animate-spin" /> Provisioning...</> : <><Rocket className="w-4 h-4" /> Provision Deployment</>}
              </button>
            </div>
          </div>
        ) : (
          /* ── Results ── */
          <div className="space-y-5">
            {/* Status banner */}
            <div className={`flex items-center gap-3 px-5 py-4 rounded-xl text-sm font-bold ${
              result.status === "success" ? "bg-emerald-50 text-emerald-800 border border-emerald-200" :
              result.status === "partial" ? "bg-amber-50 text-amber-800 border border-amber-200" :
              "bg-red-50 text-red-800 border border-red-200"
            }`}>
              {result.status === "success" ? <CheckCircle2 className="w-6 h-6" /> : result.status === "partial" ? <AlertTriangle className="w-6 h-6" /> : <XCircle className="w-6 h-6" />}
              {result.status === "success" ? "Deployment completed successfully" :
               result.status === "partial" ? "Deployment partially succeeded" :
               `Deployment failed${result.error ? `: ${result.error}` : ""}`}
            </div>

            {/* Steps */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-2">
              <div className="text-xs font-bold text-gray-700 uppercase tracking-wide mb-3">Steps</div>
              {STEP_ORDER.filter(k => result.steps?.[k]).map(k => (
                <StepResult key={k} stepKey={k} value={result.steps[k]} />
              ))}
            </div>

            {/* Customer + Site */}
            {(result.customer || result.site) && (
              <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-2">
                <div className="text-xs font-bold text-gray-700 uppercase tracking-wide mb-2">Created</div>
                {result.customer && (
                  <div className="text-sm text-gray-800"><span className="text-gray-400">Customer:</span> {result.customer.name}</div>
                )}
                {result.site && (
                  <div className="text-sm text-gray-800"><span className="text-gray-400">Site:</span> {result.site.site_name} <span className="font-mono text-gray-500">({result.site.site_id})</span></div>
                )}
              </div>
            )}

            {/* Devices */}
            {result.devices?.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-bold text-gray-700 uppercase tracking-wide">Devices</div>
                {result.devices.map(d => (
                  <DeviceResult key={d.device_sn} d={d} />
                ))}
              </div>
            )}

            {/* User invite */}
            {result.user_invite && (
              <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
                <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
                  <User className="w-4 h-4 text-red-600" /> User Account
                </div>
                {result.user_invite.status === "created" ? (
                  <>
                    <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800 font-semibold">
                      Save these credentials now — the temporary password will not be shown again.
                    </div>
                    <CopyField label="Email" value={result.user_invite.email} />
                    <CopyField label="Temporary Password" value={result.user_invite.temp_password} />
                    <CopyField label="Invite Token" value={result.user_invite.invite_token} />
                  </>
                ) : (
                  <div className="text-sm text-gray-600">
                    User <span className="font-semibold">{result.user_invite.email}</span> already exists.
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-gray-100">
              <div className="flex items-center gap-3">
                <Link to={createPageUrl("Devices")} className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 font-medium">
                  <ExternalLink className="w-3 h-3" /> View Devices
                </Link>
                <Link to={createPageUrl("VolaIntegration")} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 font-medium">
                  <ExternalLink className="w-3 h-3" /> Advanced VOLA
                </Link>
              </div>
              <button onClick={handleReset} className="px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-semibold">
                New Deployment
              </button>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}
