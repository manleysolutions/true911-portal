import { useState, useEffect, useCallback } from "react";
import { Site, Device, Line, Event } from "@/api/entities";
import { Rocket, Building2, Cpu, Phone, MapPin, Bell, CheckCircle2, ChevronRight, ChevronLeft, Loader2 } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

const STEPS = [
  { key: "site", label: "Site", icon: Building2, desc: "Customer location" },
  { key: "device", label: "Device", icon: Cpu, desc: "Edge hardware" },
  { key: "line", label: "Line", icon: Phone, desc: "Voice line / DID" },
  { key: "e911", label: "E911", icon: MapPin, desc: "Emergency address" },
  { key: "alerts", label: "Alerts", icon: Bell, desc: "Notification rules" },
  { key: "review", label: "Review", icon: CheckCircle2, desc: "Activate" },
];

const DEVICE_TYPES = [
  { value: "PR12", label: "PR12 Cellular Router" },
  { value: "ATA", label: "ATA (Analog Telephone Adapter)" },
  { value: "Elevator Panel", label: "Elevator Panel" },
  { value: "FACP", label: "Fire Alarm Control Panel" },
  { value: "Digi", label: "Digi Cellular Gateway" },
  { value: "ATEL", label: "ATEL Device" },
  { value: "Other", label: "Other" },
];

function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-1 mb-8">
      {STEPS.map((s, i) => {
        const Icon = s.icon;
        const done = i < current;
        const active = i === current;
        return (
          <div key={s.key} className="flex items-center gap-1">
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              done ? "bg-emerald-50 text-emerald-700" :
              active ? "bg-red-50 text-red-700 ring-2 ring-red-200" :
              "bg-gray-50 text-gray-400"
            }`}>
              {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && <ChevronRight className="w-3 h-3 text-gray-300" />}
          </div>
        );
      })}
    </div>
  );
}

function StepSite({ data, setData, existingSites }) {
  const [useExisting, setUseExisting] = useState(!!data.site_id);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Step 1: Site</h2>
      <p className="text-sm text-gray-500">Create a new site or select an existing one.</p>

      <div className="flex gap-3">
        <button onClick={() => setUseExisting(false)}
          className={`flex-1 p-3 rounded-xl border text-sm font-medium transition-all ${!useExisting ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
          Create New
        </button>
        <button onClick={() => setUseExisting(true)}
          className={`flex-1 p-3 rounded-xl border text-sm font-medium transition-all ${useExisting ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
          Select Existing
        </button>
      </div>

      {useExisting ? (
        <select value={data.site_id || ""} onChange={e => {
          const s = existingSites.find(x => x.site_id === e.target.value);
          setData(d => ({
            ...d,
            site_id: e.target.value,
            site_name: s?.site_name || "",
            site_address: s?.e911_street || "",
            site_city: s?.e911_city || "",
            site_state: s?.e911_state || "",
            site_zip: s?.e911_zip || "",
          }));
        }}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500">
          <option value="">-- Select a site --</option>
          {existingSites.map(s => <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id})</option>)}
        </select>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Site ID *</label>
              <input value={data.new_site_id || ""} onChange={e => setData(d => ({ ...d, new_site_id: e.target.value }))}
                placeholder="e.g. SITE-026" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Site Name *</label>
              <input value={data.site_name || ""} onChange={e => setData(d => ({ ...d, site_name: e.target.value }))}
                placeholder="e.g. 123 Main St Elevator" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Customer Name</label>
            <input value={data.customer_name || ""} onChange={e => setData(d => ({ ...d, customer_name: e.target.value }))}
              placeholder="e.g. Acme Properties LLC" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Street Address</label>
              <input value={data.site_address || ""} onChange={e => setData(d => ({ ...d, site_address: e.target.value }))}
                placeholder="1234 Main St" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
            <input value={data.site_city || ""} onChange={e => setData(d => ({ ...d, site_city: e.target.value }))}
              placeholder="City" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
            <div className="flex gap-2">
              <input value={data.site_state || ""} onChange={e => setData(d => ({ ...d, site_state: e.target.value }))}
                placeholder="ST" maxLength={2} className="w-20 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 uppercase" />
              <input value={data.site_zip || ""} onChange={e => setData(d => ({ ...d, site_zip: e.target.value }))}
                placeholder="ZIP" className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StepDevice({ data, setData }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Step 2: Device</h2>
      <p className="text-sm text-gray-500">Register the edge hardware at this site.</p>

      <div>
        <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Device Type *</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {DEVICE_TYPES.map(dt => (
            <button key={dt.value} onClick={() => setData(d => ({ ...d, device_type: dt.value }))}
              className={`p-3 rounded-xl border text-sm font-medium text-left transition-all ${
                data.device_type === dt.value ? "border-red-300 bg-red-50 text-red-700" : "border-gray-200 text-gray-600 hover:border-gray-300"
              }`}>
              {dt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Device ID *</label>
          <input value={data.device_id || ""} onChange={e => setData(d => ({ ...d, device_id: e.target.value }))}
            placeholder="e.g. DEV-026" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">IMEI</label>
          <input value={data.imei || ""} onChange={e => setData(d => ({ ...d, imei: e.target.value }))}
            placeholder="15-digit IMEI" maxLength={15} className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Serial Number</label>
          <input value={data.serial_number || ""} onChange={e => setData(d => ({ ...d, serial_number: e.target.value }))}
            placeholder="Board serial" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Model</label>
          <input value={data.model || ""} onChange={e => setData(d => ({ ...d, model: e.target.value }))}
            placeholder="e.g. PR12, OBi200" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
      </div>

      {data.device_type === "FACP" && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-700">
          <strong>NFPA 72 Note:</strong> Fire alarm panels require 5-minute supervision intervals and dual-line backup per NFPA 72 monitoring requirements.
        </div>
      )}
      {(data.device_type === "Elevator Panel" || data.device_type === "PR12") && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-700">
          <strong>Elevator Note:</strong> Test the call button after installation. Ensure AHJ (Authority Having Jurisdiction) compliance for your jurisdiction.
        </div>
      )}
    </div>
  );
}

function StepLine({ data, setData }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Step 3: Voice Line</h2>
      <p className="text-sm text-gray-500">Provision a voice line / DID for this device.</p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Line ID *</label>
          <input value={data.line_id || ""} onChange={e => setData(d => ({ ...d, line_id: e.target.value }))}
            placeholder="e.g. LINE-026" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">DID / Phone *</label>
          <input value={data.did || ""} onChange={e => setData(d => ({ ...d, did: e.target.value }))}
            placeholder="+12145550101" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Provider</label>
          <select value={data.provider || "telnyx"} onChange={e => setData(d => ({ ...d, provider: e.target.value }))}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500">
            <option value="telnyx">Telnyx</option>
            <option value="tmobile">T-Mobile</option>
            <option value="bandwidth">Bandwidth</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Protocol</label>
          <select value={data.protocol || "SIP"} onChange={e => setData(d => ({ ...d, protocol: e.target.value }))}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500">
            <option value="SIP">SIP</option>
            <option value="POTS">POTS</option>
            <option value="cellular">Cellular</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">SIP URI</label>
        <input value={data.sip_uri || ""} onChange={e => setData(d => ({ ...d, sip_uri: e.target.value }))}
          placeholder="sip:2145550101@sip.telnyx.com" className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
      </div>
    </div>
  );
}

function StepE911({ data, setData }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Step 4: E911 Address</h2>
      <p className="text-sm text-gray-500">
        Set the E911 address for this line. This will be sent to the carrier for provisioning.
        {data.site_address && " Pre-filled from site address."}
      </p>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">Street Address *</label>
          <input value={data.e911_street || data.site_address || ""} onChange={e => setData(d => ({ ...d, e911_street: e.target.value }))}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">City *</label>
            <input value={data.e911_city || data.site_city || ""} onChange={e => setData(d => ({ ...d, e911_city: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
          </div>
          <div className="flex gap-2">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">State *</label>
              <input value={data.e911_state || data.site_state || ""} onChange={e => setData(d => ({ ...d, e911_state: e.target.value }))}
                maxLength={2} className="w-20 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 uppercase" />
            </div>
            <div className="flex-1">
              <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">ZIP *</label>
              <input value={data.e911_zip || data.site_zip || ""} onChange={e => setData(d => ({ ...d, e911_zip: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
            </div>
          </div>
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-700">
        <strong>Note:</strong> E911 address will be submitted as "pending" and requires carrier validation.
        Status will update to "validated" once the carrier confirms the address.
      </div>
    </div>
  );
}

function StepAlerts({ data, setData }) {
  const templates = [
    { key: "offline", label: "Device Offline", desc: "Alert when device goes offline for 30+ minutes", default: true },
    { key: "line_down", label: "Line Down", desc: "Alert when voice line loses SIP registration", default: true },
    { key: "call_button", label: "Call Button Pressed", desc: "Log when elevator call button is pressed", default: data.device_type === "Elevator Panel" || data.device_type === "PR12" },
  ];

  const selected = data.alert_templates || templates.filter(t => t.default).map(t => t.key);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Step 5: Alert Rules</h2>
      <p className="text-sm text-gray-500">Quick-add common alert templates. You can customize these later in Alerts.</p>

      <div className="space-y-2">
        {templates.map(t => (
          <label key={t.key} className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
            selected.includes(t.key) ? "border-red-300 bg-red-50" : "border-gray-200 hover:border-gray-300"
          }`}>
            <input type="checkbox" checked={selected.includes(t.key)}
              onChange={() => {
                const next = selected.includes(t.key) ? selected.filter(k => k !== t.key) : [...selected, t.key];
                setData(d => ({ ...d, alert_templates: next }));
              }}
              className="mt-0.5 accent-red-600" />
            <div>
              <div className="text-sm font-semibold text-gray-900">{t.label}</div>
              <div className="text-xs text-gray-500">{t.desc}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

function StepReview({ data, existingSites }) {
  const siteName = data.site_id
    ? existingSites.find(s => s.site_id === data.site_id)?.site_name || data.site_id
    : data.site_name || "New Site";

  const items = [
    { label: "Site", value: siteName },
    { label: "Device", value: `${data.device_type || "---"} — ${data.device_id || "---"}` },
    { label: "IMEI", value: data.imei || "Not set" },
    { label: "Line", value: `${data.did || "---"} (${data.provider || "telnyx"}, ${data.protocol || "SIP"})` },
    { label: "E911", value: [data.e911_street || data.site_address, data.e911_city || data.site_city, data.e911_state || data.site_state, data.e911_zip || data.site_zip].filter(Boolean).join(", ") || "Not set" },
    { label: "Alerts", value: (data.alert_templates || []).join(", ") || "None" },
  ];

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900">Step 6: Review & Activate</h2>
      <p className="text-sm text-gray-500">Review your configuration before creating all resources.</p>

      <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        {items.map(i => (
          <div key={i.label} className="flex items-center justify-between px-4 py-3">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{i.label}</span>
            <span className="text-sm text-gray-800">{i.value}</span>
          </div>
        ))}
      </div>

      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs text-emerald-700">
        <strong>Ready to activate.</strong> This will create the site (if new), register the device,
        provision the voice line, submit E911, and configure alert rules.
      </div>
    </div>
  );
}

export default function OnboardingWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [data, setData] = useState({ provider: "telnyx", protocol: "SIP" });
  const [sites, setSites] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const fetchSites = useCallback(async () => {
    const s = await Site.list("-last_checkin", 200);
    setSites(s);
  }, []);

  useEffect(() => { fetchSites(); }, [fetchSites]);

  const handleNext = () => setStep(s => Math.min(s + 1, STEPS.length - 1));
  const handleBack = () => setStep(s => Math.max(s - 1, 0));

  const handleActivate = async () => {
    setError("");
    setSubmitting(true);
    try {
      // 1. Create site if new
      let siteId = data.site_id;
      if (!siteId && data.new_site_id) {
        const site = await Site.create({
          site_id: data.new_site_id,
          site_name: data.site_name,
          customer_name: data.customer_name || undefined,
          e911_street: data.site_address || undefined,
          e911_city: data.site_city || undefined,
          e911_state: data.site_state || undefined,
          e911_zip: data.site_zip || undefined,
          status: "Connected",
        });
        siteId = site.site_id;
      }

      // 2. Create device
      if (data.device_id) {
        await Device.create({
          device_id: data.device_id,
          site_id: siteId || undefined,
          device_type: data.device_type || "Other",
          model: data.model || data.device_type,
          imei: data.imei || undefined,
          serial_number: data.serial_number || undefined,
          status: "provisioning",
        });
      }

      // 3. Create line
      if (data.line_id && data.did) {
        await Line.create({
          line_id: data.line_id,
          site_id: siteId || undefined,
          device_id: data.device_id || undefined,
          provider: data.provider || "telnyx",
          did: data.did,
          sip_uri: data.sip_uri || undefined,
          protocol: data.protocol || "SIP",
          e911_street: data.e911_street || data.site_address || undefined,
          e911_city: data.e911_city || data.site_city || undefined,
          e911_state: data.e911_state || data.site_state || undefined,
          e911_zip: data.e911_zip || data.site_zip || undefined,
        });
      }

      // 4. Create activation event
      await Event.create({
        event_id: `EVT-ONBOARD-${Date.now()}`,
        event_type: "device.registered",
        site_id: siteId || undefined,
        device_id: data.device_id || undefined,
        line_id: data.line_id || undefined,
        severity: "info",
        message: `Onboarding completed: ${data.device_type || "device"} ${data.device_id || ""} at ${data.site_name || siteId || "site"}`,
      });

      toast.success("Onboarding complete! Device, line, and E911 created.");
      navigate("/Devices");
    } catch (err) {
      setError(err?.message || "Activation failed. Check the details and try again.");
      setSubmitting(false);
    }
  };

  const stepComponents = [
    <StepSite data={data} setData={setData} existingSites={sites} />,
    <StepDevice data={data} setData={setData} />,
    <StepLine data={data} setData={setData} />,
    <StepE911 data={data} setData={setData} />,
    <StepAlerts data={data} setData={setData} />,
    <StepReview data={data} existingSites={sites} />,
  ];

  return (
    <PageWrapper>
      <div className="p-6 max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-2">
          <Rocket className="w-5 h-5 text-red-600" />
          <h1 className="text-2xl font-bold text-gray-900">Onboarding Wizard</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">Set up a new site with device, voice line, E911, and alerts in one go.</p>

        <StepIndicator current={step} />

        <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-6">
          {stepComponents[step]}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl mb-4">{error}</div>
        )}

        <div className="flex items-center justify-between">
          <button onClick={handleBack} disabled={step === 0}
            className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-gray-600 border border-gray-200 rounded-xl hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">
            <ChevronLeft className="w-4 h-4" /> Back
          </button>

          {step < STEPS.length - 1 ? (
            <button onClick={handleNext}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-xl">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={handleActivate} disabled={submitting}
              className="flex items-center gap-1.5 px-6 py-2.5 text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 rounded-xl">
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Activating...</> : <><CheckCircle2 className="w-4 h-4" /> Activate</>}
            </button>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
