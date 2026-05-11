/**
 * Self-service customer registration wizard (Phase R2).
 *
 * Public, anonymous, customer-facing.  Walks a non-technical user
 * through 10 short screens, persisting state to sessionStorage on
 * every change so that an accidental refresh doesn't lose progress.
 *
 * On the final step the wizard makes exactly two API calls:
 *   1. POST /public/registrations  — creates the staged record
 *      including all locations and service units
 *   2. POST /public/registrations/{id}/submit  — flips status to
 *      "submitted" and locks the public surface
 *
 * No production rows (customers, sites, service_units, devices,
 * users) are created on this surface.  Conversion is a later phase.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Shield, ArrowLeft, ArrowRight, CheckCircle2, AlertTriangle, Plus, Trash2,
  Building2, User, Phone, MapPin, Cpu, Calendar, CreditCard, ClipboardCheck,
  HelpCircle, Loader2, ChevronRight,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";
import { RegistrationAPI } from "@/api/registrations";

// ── Constants ────────────────────────────────────────────────────────

const DRAFT_KEY = "t911_registration_draft_v1";

const STEPS = [
  { key: "welcome",   label: "Welcome",       icon: Shield,         help: "A quick overview of what we'll collect." },
  { key: "customer",  label: "Your Company",  icon: Building2,      help: "Tell us who you are and how to reach you." },
  { key: "contact",   label: "Main Contact",  icon: User,           help: "Who should we call about installation and service?" },
  { key: "locations", label: "Locations",     icon: MapPin,         help: "Where are we installing the emergency phones?" },
  { key: "units",     label: "Phones/Units",  icon: Phone,          help: "How many emergency phones at each location?" },
  { key: "device",    label: "Equipment",     icon: Cpu,            help: "Tell us your equipment & carrier preferences." },
  { key: "e911",      label: "E911 Details",  icon: MapPin,         help: "Where exactly is each phone located inside the building?" },
  { key: "schedule",  label: "Scheduling",    icon: Calendar,       help: "When would you like the installation?" },
  { key: "billing",   label: "Billing",       icon: CreditCard,     help: "How would you like to be billed?" },
  { key: "review",    label: "Review",        icon: ClipboardCheck, help: "One last look before submitting." },
];

const UNIT_TYPE_OPTIONS = [
  { value: "elevator_phone",         label: "Elevator Emergency Phone" },
  { value: "fire_alarm",             label: "Fire Alarm Communicator" },
  { value: "emergency_call_station", label: "Emergency Call Station" },
  { value: "fax_line",               label: "Fax Line" },
  { value: "voice_line",             label: "Generic Voice Line" },
  { value: "other",                  label: "Other / Not Sure" },
];

const PLAN_OPTIONS = [
  { value: "monitoring",       label: "Monitoring Only",         desc: "Heartbeat & alerting for each device." },
  { value: "monitoring_e911",  label: "Monitoring + E911",       desc: "Adds E911 address compliance management." },
  { value: "full_noc",         label: "Full NOC Service",        desc: "Monitoring + E911 + 24/7 incident management." },
  { value: "custom",           label: "Not Sure / Discuss",      desc: "We'll recommend the right fit on our follow-up call." },
];

const BILLING_METHOD_OPTIONS = [
  { value: "invoice",     label: "Invoice (NET 30)" },
  { value: "ach",         label: "ACH / Bank Transfer" },
  { value: "credit_card", label: "Credit Card" },
  { value: "other",       label: "Other / Discuss" },
];

const SUPPORT_CHANNEL_OPTIONS = [
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
  { value: "text",  label: "Text Message" },
];

const INITIAL_DRAFT = {
  // Step 2 — Your Company
  submitter_email: "",
  submitter_name: "",
  submitter_phone: "",
  customer_name: "",
  customer_legal_name: "",
  customer_account_number: "",
  // Step 3 — Main Contact
  poc_name: "",
  poc_phone: "",
  poc_email: "",
  poc_role: "",
  // Step 6 — Equipment / use case
  use_case_summary: "",
  hardware_request: "",
  carrier_request: "",
  // Step 8 — Scheduling
  preferred_install_window_start: "",
  preferred_install_window_end: "",
  installer_notes: "",
  // Step 9 — Billing & Support
  selected_plan_code: "",
  plan_quantity_estimate: "",
  billing_email: "",
  billing_address_street: "",
  billing_address_city: "",
  billing_address_state: "",
  billing_address_zip: "",
  billing_address_country: "US",
  billing_method: "",
  support_channels: [],
  after_hours_contact: "",
  // Step 4/5/7 — Locations & service units (client-side until submit)
  locations: [],
};

const NEW_LOCATION = () => ({
  location_label: "",
  street: "",
  city: "",
  state: "",
  zip: "",
  country: "US",
  dispatchable_description: "",
  access_notes: "",
  service_units: [],
});

const NEW_UNIT = () => ({
  unit_label: "",
  unit_type: "elevator_phone",
  phone_number_existing: "",
  quantity: 1,
});


// ── sessionStorage-backed draft hook ─────────────────────────────────

function useDraft() {
  const [draft, setDraft] = useState(() => {
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY);
      if (!raw) return { ...INITIAL_DRAFT };
      const parsed = JSON.parse(raw);
      return { ...INITIAL_DRAFT, ...parsed };
    } catch {
      return { ...INITIAL_DRAFT };
    }
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // sessionStorage can fail in private-mode Safari, full disks,
      // etc.  We never want that to break the wizard — just lose
      // resume capability silently.
    }
  }, [draft]);

  const resetDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setDraft({ ...INITIAL_DRAFT });
  };

  return { draft, setDraft, resetDraft };
}


// ── Step indicator ───────────────────────────────────────────────────

function StepIndicator({ stepIndex }) {
  const totalSteps = STEPS.length;
  const pct = Math.round(((stepIndex + 1) / totalSteps) * 100);
  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2 text-xs">
        <span className="text-slate-400">
          Step {stepIndex + 1} of {totalSteps}
        </span>
        <span className="text-red-400 font-semibold">{pct}% complete</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-red-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="hidden md:flex items-center gap-1 mt-3 overflow-x-auto pb-1">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const done = i < stepIndex;
          const active = i === stepIndex;
          return (
            <div key={s.key} className="flex items-center flex-shrink-0">
              <div
                className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  active
                    ? "bg-red-600/20 text-red-300 border border-red-500/40"
                    : done
                    ? "text-emerald-400"
                    : "text-slate-500"
                }`}
              >
                {done ? <CheckCircle2 className="w-3 h-3" /> : <Icon className="w-3 h-3" />}
                <span>{s.label}</span>
              </div>
              {i < STEPS.length - 1 && <ChevronRight className="w-3 h-3 text-slate-700 mx-0.5" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ── Reusable inputs ──────────────────────────────────────────────────

const INPUT = "w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all";
const LABEL = "block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide";

function Field({ label, value, onChange, placeholder = "", required = false, type = "text", help = null, maxLength = undefined }) {
  return (
    <div>
      <label className={LABEL}>
        {label}{required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      <input
        type={type}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={INPUT}
        maxLength={maxLength}
      />
      {help && <p className="mt-1 text-[11px] text-slate-500">{help}</p>}
    </div>
  );
}

function TextArea({ label, value, onChange, placeholder = "", rows = 3, maxLength = undefined, help = null }) {
  return (
    <div>
      <label className={LABEL}>{label}</label>
      <textarea
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        maxLength={maxLength}
        className={`${INPUT} resize-none`}
      />
      {help && <p className="mt-1 text-[11px] text-slate-500">{help}</p>}
    </div>
  );
}

function HelpBox({ children }) {
  return (
    <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3 text-xs text-blue-200">
      <HelpCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-400" />
      <div>{children}</div>
    </div>
  );
}


// ── Step screens ─────────────────────────────────────────────────────

function WelcomeStep() {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Let's get your service set up</h2>
        <p className="text-sm text-slate-400 leading-relaxed">
          We'll walk you through about 10 short questions. There's nothing
          technical to figure out — we just need to know who you are, where
          we're installing, and how you'd like us to reach you.
        </p>
      </div>

      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white">What you'll need handy</h3>
        <ul className="space-y-2 text-sm text-slate-300">
          <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" /> Company name and a billing email</li>
          <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" /> The street address of each location</li>
          <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" /> How many emergency phones at each location</li>
          <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" /> A point of contact our installer can call</li>
        </ul>
      </div>

      <HelpBox>
        <strong className="text-white">Don't worry about getting everything perfect.</strong>{" "}
        You can leave things blank where you're not sure — our team will
        follow up to confirm the details before we schedule the install.
      </HelpBox>

      <p className="text-xs text-slate-500">
        Already started?{" "}
        <Link to="/login" className="text-red-400 hover:text-red-300 font-medium">
          Sign in to your portal
        </Link>{" "}
        instead.
      </p>
    </div>
  );
}

function CustomerStep({ draft, set }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">Tell us who you are. We'll send all confirmations to the email below.</p>

      <Field
        label="Property Management / Company Name"
        value={draft.customer_name}
        onChange={set("customer_name")}
        placeholder="e.g. Integrity Property Management"
        required
        help="This is your top-level account — the management company, ownership group, or organisation. Individual buildings go in the next step."
      />

      <Field
        label="Legal / Billing Name (optional)"
        value={draft.customer_legal_name}
        onChange={set("customer_legal_name")}
        placeholder="If different from the company name"
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field
          label="Your Name"
          value={draft.submitter_name}
          onChange={set("submitter_name")}
          placeholder="Jane Smith"
          required
        />
        <Field
          label="Your Email"
          value={draft.submitter_email}
          onChange={set("submitter_email")}
          placeholder="you@example.com"
          required
          type="email"
        />
      </div>

      <Field
        label="Your Phone"
        value={draft.submitter_phone}
        onChange={set("submitter_phone")}
        placeholder="(555) 123-4567"
        type="tel"
      />

      <HelpBox>
        <strong className="text-white">Tip:</strong> Use the management
        company or ownership group here (e.g. "Integrity Property
        Management") — not the name of an individual building. You'll
        list each property separately in the next step.
      </HelpBox>
    </div>
  );
}

function ContactStep({ draft, set }) {
  const samePerson = () => {
    set("poc_name")(draft.submitter_name);
    set("poc_phone")(draft.submitter_phone);
    set("poc_email")(draft.submitter_email);
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        Who should we call on the day of installation? This can be
        you, a property manager, a maintenance contact — whoever the
        installer should coordinate with.
      </p>

      <button
        type="button"
        onClick={samePerson}
        className="text-xs text-red-400 hover:text-red-300 underline underline-offset-2"
      >
        Same as me
      </button>

      <Field
        label="Contact Name"
        value={draft.poc_name}
        onChange={set("poc_name")}
        placeholder="Cindy Whittle"
        required
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field
          label="Contact Phone"
          value={draft.poc_phone}
          onChange={set("poc_phone")}
          placeholder="954-346-0677"
          type="tel"
          required
        />
        <Field
          label="Contact Email (optional)"
          value={draft.poc_email}
          onChange={set("poc_email")}
          placeholder="contact@example.com"
          type="email"
        />
      </div>

      <Field
        label="Their Role (optional)"
        value={draft.poc_role}
        onChange={set("poc_role")}
        placeholder="Property Manager, Maintenance Lead, etc."
      />

      <HelpBox>
        The installer will text or call this person 24 hours before
        arriving on site.
      </HelpBox>
    </div>
  );
}

function LocationsStep({ draft, setDraft }) {
  const updateLocation = (idx, field, value) => {
    setDraft((d) => ({
      ...d,
      locations: d.locations.map((l, i) => (i === idx ? { ...l, [field]: value } : l)),
    }));
  };
  const addLocation = () => {
    setDraft((d) => ({ ...d, locations: [...d.locations, NEW_LOCATION()] }));
  };
  const removeLocation = (idx) => {
    setDraft((d) => ({ ...d, locations: d.locations.filter((_, i) => i !== idx) }));
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        Add each <strong className="text-white">individual building or property</strong> where
        we'll be installing emergency phones — separate from your company
        name on the previous step. If you have several buildings on
        one campus, add each one separately.
      </p>

      {draft.locations.length === 0 && (
        <div className="bg-slate-800/50 border border-dashed border-slate-700 rounded-xl p-6 text-center">
          <MapPin className="w-6 h-6 text-slate-500 mx-auto mb-2" />
          <p className="text-sm text-slate-400 mb-4">No locations added yet.</p>
          <button
            onClick={addLocation}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-lg"
          >
            <Plus className="w-4 h-4" /> Add Your First Location
          </button>
        </div>
      )}

      {draft.locations.map((loc, idx) => (
        <div key={idx} className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
              Location {idx + 1}
            </span>
            <button
              onClick={() => removeLocation(idx)}
              className="p-1.5 text-slate-500 hover:text-red-400 rounded hover:bg-red-500/10 transition-colors"
              title="Remove this location"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
          <Field
            label="Building / Property Name"
            value={loc.location_label}
            onChange={(v) => updateLocation(idx, "location_label", v)}
            placeholder="e.g. Tiffany Gardens East"
            required
            help="The specific building at this location — not your management company name."
          />
          <Field
            label="Street Address"
            value={loc.street}
            onChange={(v) => updateLocation(idx, "street", v)}
            placeholder="1234 Main Street"
          />
          <div className="grid grid-cols-3 gap-3">
            <Field
              label="City"
              value={loc.city}
              onChange={(v) => updateLocation(idx, "city", v)}
              placeholder="Tampa"
            />
            <Field
              label="State"
              value={loc.state}
              onChange={(v) => updateLocation(idx, "state", v)}
              placeholder="FL"
              maxLength={2}
            />
            <Field
              label="ZIP"
              value={loc.zip}
              onChange={(v) => updateLocation(idx, "zip", v)}
              placeholder="33601"
              maxLength={10}
            />
          </div>
        </div>
      ))}

      {draft.locations.length > 0 && (
        <button
          onClick={addLocation}
          className="inline-flex items-center gap-1.5 text-sm text-red-400 hover:text-red-300 font-medium"
        >
          <Plus className="w-4 h-4" /> Add Another Location
        </button>
      )}
    </div>
  );
}

function ServiceUnitsStep({ draft, setDraft }) {
  if (draft.locations.length === 0) {
    return (
      <div className="bg-amber-500/10 border border-amber-500/30 text-amber-200 text-sm rounded-xl px-4 py-3">
        Please add at least one location before listing your emergency phones.
      </div>
    );
  }

  const updateUnit = (locIdx, unitIdx, field, value) => {
    setDraft((d) => ({
      ...d,
      locations: d.locations.map((l, i) =>
        i !== locIdx
          ? l
          : {
              ...l,
              service_units: l.service_units.map((u, j) =>
                j !== unitIdx ? u : { ...u, [field]: value }
              ),
            }
      ),
    }));
  };
  const addUnit = (locIdx) => {
    setDraft((d) => ({
      ...d,
      locations: d.locations.map((l, i) =>
        i !== locIdx
          ? l
          : { ...l, service_units: [...l.service_units, NEW_UNIT()] }
      ),
    }));
  };
  const removeUnit = (locIdx, unitIdx) => {
    setDraft((d) => ({
      ...d,
      locations: d.locations.map((l, i) =>
        i !== locIdx
          ? l
          : { ...l, service_units: l.service_units.filter((_, j) => j !== unitIdx) }
      ),
    }));
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        For each location, list the emergency phones (or other service
        units) you need. If you already have phone numbers assigned to
        these phones, enter them too — we'll port them over.
      </p>

      {draft.locations.map((loc, locIdx) => (
        <div key={locIdx} className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-red-400" />
            <h3 className="text-sm font-semibold text-white">{loc.location_label || `Location ${locIdx + 1}`}</h3>
          </div>

          {loc.service_units.length === 0 && (
            <p className="text-xs text-slate-500">No units added yet for this location.</p>
          )}

          {loc.service_units.map((unit, unitIdx) => (
            <div key={unitIdx} className="bg-slate-900/40 border border-slate-700/40 rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-slate-500 uppercase">Unit {unitIdx + 1}</span>
                <button
                  onClick={() => removeUnit(locIdx, unitIdx)}
                  className="p-1 text-slate-500 hover:text-red-400 rounded hover:bg-red-500/10"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field
                  label="Unit Label"
                  value={unit.unit_label}
                  onChange={(v) => updateUnit(locIdx, unitIdx, "unit_label", v)}
                  placeholder="e.g. TGE1"
                  required
                />
                <div>
                  <label className={LABEL}>Type</label>
                  <select
                    value={unit.unit_type}
                    onChange={(e) => updateUnit(locIdx, unitIdx, "unit_type", e.target.value)}
                    className={INPUT}
                  >
                    {UNIT_TYPE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <Field
                label="Existing Phone Number (optional)"
                value={unit.phone_number_existing}
                onChange={(v) => updateUnit(locIdx, unitIdx, "phone_number_existing", v)}
                placeholder="9543129018"
                help="If this phone already has a number, we can keep it."
              />
            </div>
          ))}

          <button
            onClick={() => addUnit(locIdx)}
            className="inline-flex items-center gap-1.5 text-sm text-red-400 hover:text-red-300 font-medium"
          >
            <Plus className="w-3.5 h-3.5" /> Add Emergency Phone to "{loc.location_label || `Location ${locIdx + 1}`}"
          </button>
        </div>
      ))}
    </div>
  );
}

function DeviceStep({ draft, set }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        If you already have a preferred equipment model or carrier, tell
        us here. Otherwise leave these blank — our team will recommend
        the right setup for your buildings.
      </p>

      <Field
        label="Preferred Equipment (optional)"
        value={draft.hardware_request}
        onChange={set("hardware_request")}
        placeholder="e.g. MS130v4"
        help="The model of cellular emergency phone adapter you'd like, if you know."
      />

      <Field
        label="Preferred Carrier (optional)"
        value={draft.carrier_request}
        onChange={set("carrier_request")}
        placeholder="e.g. T-Mobile"
        help="Which cellular carrier should the device use?"
      />

      <TextArea
        label="Anything Else We Should Know?"
        value={draft.use_case_summary}
        onChange={set("use_case_summary")}
        placeholder="Number of elevators, special access requirements, jurisdiction notes…"
        rows={3}
        maxLength={8000}
      />
    </div>
  );
}

function E911Step({ draft, setDraft }) {
  const updateLocation = (idx, field, value) => {
    setDraft((d) => ({
      ...d,
      locations: d.locations.map((l, i) => (i === idx ? { ...l, [field]: value } : l)),
    }));
  };

  if (draft.locations.length === 0) {
    return (
      <div className="bg-amber-500/10 border border-amber-500/30 text-amber-200 text-sm rounded-xl px-4 py-3">
        Add at least one location to fill out E911 details.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        For 911 dispatch to find the phone quickly, we need to know
        exactly where in the building it lives. Floor numbers, suite
        numbers, and any access notes (gate code, parking, key location)
        are all helpful.
      </p>

      <HelpBox>
        These details are sent to emergency dispatchers so they can
        reach the right place when 911 is called.
      </HelpBox>

      {draft.locations.map((loc, idx) => (
        <div key={idx} className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-red-400" />
            <h3 className="text-sm font-semibold text-white">{loc.location_label || `Location ${idx + 1}`}</h3>
          </div>

          <TextArea
            label="Where exactly is each phone? (e.g. floor, suite, elevator car #)"
            value={loc.dispatchable_description}
            onChange={(v) => updateLocation(idx, "dispatchable_description", v)}
            placeholder="Elevator #1 — South Tower, Cars 1 and 2"
            rows={2}
            maxLength={4000}
          />

          <TextArea
            label="Access Notes (optional)"
            value={loc.access_notes}
            onChange={(v) => updateLocation(idx, "access_notes", v)}
            placeholder="Gate code 1234, park in visitor lot, key at front desk…"
            rows={2}
            maxLength={4000}
          />
        </div>
      ))}
    </div>
  );
}

function ScheduleStep({ draft, set }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        When would you like the installation to happen? We use a network
        of local installers, so we'll work with their schedule and
        confirm the exact day with you before we send anyone out.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field
          label="Earliest Preferred Date"
          value={draft.preferred_install_window_start ? draft.preferred_install_window_start.slice(0, 10) : ""}
          onChange={(v) => set("preferred_install_window_start")(v ? `${v}T08:00:00` : "")}
          type="date"
        />
        <Field
          label="Latest Acceptable Date"
          value={draft.preferred_install_window_end ? draft.preferred_install_window_end.slice(0, 10) : ""}
          onChange={(v) => set("preferred_install_window_end")(v ? `${v}T17:00:00` : "")}
          type="date"
        />
      </div>

      <TextArea
        label="Anything special the installer should know?"
        value={draft.installer_notes}
        onChange={set("installer_notes")}
        placeholder="Best to arrive after 10am; building has loading dock on the east side…"
        rows={3}
        maxLength={4000}
      />

      <HelpBox>
        We dispatch installers through a partner network. After you
        submit, our team will confirm the schedule and send you
        installer details by email.
      </HelpBox>
    </div>
  );
}

function BillingStep({ draft, set, setDraft }) {
  const toggleChannel = (val) => {
    const current = draft.support_channels || [];
    const next = current.includes(val) ? current.filter((c) => c !== val) : [...current, val];
    setDraft((d) => ({ ...d, support_channels: next }));
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        Last bit: how would you like to be billed, and how should we
        reach you if there's a service issue?
      </p>

      <div>
        <label className={LABEL}>Service Level</label>
        <div className="space-y-2">
          {PLAN_OPTIONS.map((p) => (
            <label
              key={p.value}
              className={`flex items-start gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-all ${
                draft.selected_plan_code === p.value
                  ? "bg-red-600/15 border-red-500/40"
                  : "bg-slate-900/30 border-slate-700/50 hover:border-slate-600"
              }`}
            >
              <input
                type="radio"
                name="plan"
                value={p.value}
                checked={draft.selected_plan_code === p.value}
                onChange={() => set("selected_plan_code")(p.value)}
                className="mt-0.5 accent-red-600"
              />
              <div>
                <div className="text-sm font-medium text-white">{p.label}</div>
                <div className="text-xs text-slate-400">{p.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div>
        <label className={LABEL}>How Would You Like To Be Billed?</label>
        <div className="grid grid-cols-2 gap-2">
          {BILLING_METHOD_OPTIONS.map((b) => (
            <button
              key={b.value}
              type="button"
              onClick={() => set("billing_method")(b.value)}
              className={`px-3 py-2.5 rounded-lg text-xs text-left transition-all border ${
                draft.billing_method === b.value
                  ? "bg-red-600/15 border-red-500/40 text-red-300"
                  : "bg-slate-900/30 border-slate-700/50 text-slate-400 hover:border-slate-600"
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      <Field
        label="Billing Email"
        value={draft.billing_email}
        onChange={set("billing_email")}
        placeholder="ap@example.com"
        type="email"
        help="Where should invoices go? Leave blank to use your email above."
      />

      <Field
        label="Billing Address (street, city, state, zip)"
        value={draft.billing_address_street}
        onChange={set("billing_address_street")}
        placeholder="Optional — useful for invoicing"
      />
      <div className="grid grid-cols-3 gap-3">
        <Field label="City" value={draft.billing_address_city} onChange={set("billing_address_city")} />
        <Field label="State" value={draft.billing_address_state} onChange={set("billing_address_state")} maxLength={2} />
        <Field label="ZIP" value={draft.billing_address_zip} onChange={set("billing_address_zip")} maxLength={10} />
      </div>

      <div>
        <label className={LABEL}>Preferred Support Channels</label>
        <div className="flex flex-wrap gap-2">
          {SUPPORT_CHANNEL_OPTIONS.map((c) => {
            const on = (draft.support_channels || []).includes(c.value);
            return (
              <button
                key={c.value}
                type="button"
                onClick={() => toggleChannel(c.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  on
                    ? "bg-red-600/15 border-red-500/40 text-red-300"
                    : "bg-slate-900/30 border-slate-700/50 text-slate-400 hover:border-slate-600"
                }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      <Field
        label="After-Hours Contact (optional)"
        value={draft.after_hours_contact}
        onChange={set("after_hours_contact")}
        placeholder="Name and phone for nights/weekends"
      />
    </div>
  );
}

function ReviewStep({ draft }) {
  const totalUnits = draft.locations.reduce((acc, l) => acc + l.service_units.length, 0);
  const warnings = [];
  if (!draft.customer_name) warnings.push("Company name is missing.");
  if (!draft.submitter_email) warnings.push("Your email is missing.");
  if (!draft.poc_name) warnings.push("A point of contact name is missing.");
  if (draft.locations.length === 0) warnings.push("No locations added yet.");
  if (totalUnits === 0) warnings.push("No emergency phones listed.");

  const Row = ({ label, value }) => (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-slate-800 last:border-b-0">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <span className="text-sm text-slate-200 text-right">{value || <span className="text-slate-600 italic">not set</span>}</span>
    </div>
  );

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        Here's a quick look at what you've filled out. If anything is
        wrong, click <strong className="text-white">Back</strong> to fix
        it before submitting.
      </p>

      <div className="grid grid-cols-3 gap-3">
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-white">{draft.locations.length}</div>
          <div className="text-[10px] text-slate-500 uppercase font-semibold">Locations</div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-white">{totalUnits}</div>
          <div className="text-[10px] text-slate-500 uppercase font-semibold">Emergency Phones</div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3 text-center">
          <div className="text-2xl font-bold text-white capitalize">
            {(draft.selected_plan_code || "—").replace(/_/g, " ")}
          </div>
          <div className="text-[10px] text-slate-500 uppercase font-semibold">Plan</div>
        </div>
      </div>

      <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Building2 className="w-4 h-4 text-red-400" /> Company
        </h3>
        <Row label="Company" value={draft.customer_name} />
        <Row label="Your Name" value={draft.submitter_name} />
        <Row label="Your Email" value={draft.submitter_email} />
        <Row label="Your Phone" value={draft.submitter_phone} />
      </div>

      <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <User className="w-4 h-4 text-red-400" /> Main Contact
        </h3>
        <Row label="Name" value={draft.poc_name} />
        <Row label="Phone" value={draft.poc_phone} />
        <Row label="Email" value={draft.poc_email} />
        <Row label="Role" value={draft.poc_role} />
      </div>

      <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <MapPin className="w-4 h-4 text-red-400" /> Locations & Phones
        </h3>
        {draft.locations.length === 0 ? (
          <p className="text-sm text-slate-500 italic">No locations yet.</p>
        ) : (
          <div className="space-y-3">
            {draft.locations.map((l, i) => (
              <div key={i} className="text-sm">
                <div className="text-white font-medium">{l.location_label || `Location ${i + 1}`}</div>
                <div className="text-xs text-slate-500">
                  {[l.street, l.city, l.state, l.zip].filter(Boolean).join(", ") || "Address not set"}
                </div>
                <ul className="mt-1 ml-2 text-xs text-slate-300">
                  {l.service_units.map((u, j) => (
                    <li key={j}>
                      • {u.unit_label || `Unit ${j + 1}`}
                      {u.phone_number_existing ? ` (${u.phone_number_existing})` : ""}
                    </li>
                  ))}
                  {l.service_units.length === 0 && <li className="italic text-slate-600">No phones listed.</li>}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      {warnings.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-xs text-amber-200">
          <div className="flex items-center gap-2 font-semibold mb-1">
            <AlertTriangle className="w-3.5 h-3.5" /> A few items still need attention:
          </div>
          <ul className="space-y-1 ml-5 list-disc">
            {warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
          <p className="mt-2 text-amber-300/80">
            You can still submit — our team will reach out to confirm
            anything that's missing.
          </p>
        </div>
      )}

      <HelpBox>
        After you click <strong className="text-white">Submit</strong>,
        we'll save your request and our team will follow up within one
        business day to confirm everything and schedule your installation.
      </HelpBox>
    </div>
  );
}


// ── Payload builder ──────────────────────────────────────────────────

/** Translate the wizard's client-side draft into the JSON the backend
 *  POST /api/public/registrations endpoint expects.  Empty strings
 *  become null/omitted so they don't get persisted as "" in Postgres.
 */
function buildPayload(draft) {
  const clean = (v) => (v === "" || v == null ? undefined : v);
  const cleanEmail = (v) => clean((v || "").trim().toLowerCase()) || undefined;
  const numberOrUndef = (v) => {
    if (v === "" || v == null) return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  };

  // Hardware and carrier preferences are captured globally in the
  // wizard but the backend stores them per-service-unit.  Stamp every
  // unit with the same value at POST time.
  const hardware = clean(draft.hardware_request);
  const carrier = clean(draft.carrier_request);

  const support_preference_json = (() => {
    const sp = {};
    if (draft.support_channels && draft.support_channels.length) sp.channels = draft.support_channels;
    if (clean(draft.after_hours_contact)) sp.after_hours_contact = draft.after_hours_contact;
    return Object.keys(sp).length ? sp : undefined;
  })();

  return {
    submitter_email: cleanEmail(draft.submitter_email),
    submitter_name: clean(draft.submitter_name),
    submitter_phone: clean(draft.submitter_phone),
    customer_name: clean(draft.customer_name),
    customer_legal_name: clean(draft.customer_legal_name),
    customer_account_number: clean(draft.customer_account_number),

    poc_name: clean(draft.poc_name),
    poc_phone: clean(draft.poc_phone),
    poc_email: cleanEmail(draft.poc_email),
    poc_role: clean(draft.poc_role),

    use_case_summary: clean(draft.use_case_summary),
    selected_plan_code: clean(draft.selected_plan_code),
    plan_quantity_estimate: numberOrUndef(draft.plan_quantity_estimate),

    billing_email: cleanEmail(draft.billing_email),
    billing_address_street: clean(draft.billing_address_street),
    billing_address_city: clean(draft.billing_address_city),
    billing_address_state: clean(draft.billing_address_state),
    billing_address_zip: clean(draft.billing_address_zip),
    billing_address_country: clean(draft.billing_address_country),
    billing_method: clean(draft.billing_method),

    support_preference_json,

    preferred_install_window_start: clean(draft.preferred_install_window_start),
    preferred_install_window_end: clean(draft.preferred_install_window_end),
    installer_notes: clean(draft.installer_notes),

    locations: (draft.locations || []).map((loc) => ({
      location_label: loc.location_label || "Unnamed location",
      street: clean(loc.street),
      city: clean(loc.city),
      state: clean(loc.state),
      zip: clean(loc.zip),
      country: clean(loc.country),
      dispatchable_description: clean(loc.dispatchable_description),
      access_notes: clean(loc.access_notes),
      service_units: (loc.service_units || []).map((unit) => ({
        unit_label: unit.unit_label || "Unnamed unit",
        unit_type: unit.unit_type || "other",
        phone_number_existing: clean(unit.phone_number_existing),
        hardware_model_request: hardware,
        carrier_request: carrier,
        quantity: unit.quantity || 1,
      })),
    })),
  };
}


// ── Main wizard component ────────────────────────────────────────────

export default function Register() {
  const navigate = useNavigate();
  const { draft, setDraft, resetDraft } = useDraft();
  const [stepIndex, setStepIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Curried setter — `set("field")` returns a value->void function
  // suitable for passing directly to a Field component.
  const set = useMemo(
    () => (field) => (value) => setDraft((d) => ({ ...d, [field]: value })),
    [setDraft],
  );

  const step = STEPS[stepIndex];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;

  // Per-step "can advance" gate.  Keep it permissive — non-technical
  // users hate red-validation surprises.  Hard validation lives on the
  // server (and produces a friendly error at submit time).
  const canAdvance = useMemo(() => {
    if (step.key === "customer") {
      return !!(draft.customer_name && draft.submitter_email && draft.submitter_name);
    }
    if (step.key === "contact") {
      return !!(draft.poc_name && draft.poc_phone);
    }
    return true;
  }, [step.key, draft]);

  const goNext = () => setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  const goBack = () => setStepIndex((i) => Math.max(i - 1, 0));

  const handleSubmit = async () => {
    setError("");
    setSubmitting(true);
    try {
      const payload = buildPayload(draft);
      const created = await RegistrationAPI.create(payload);
      const regId = created?.registration?.registration_id;
      const token = created?.resume_token;
      if (!regId || !token) {
        throw new Error("Unexpected response from server. Please try again.");
      }

      // Persist the just-issued id+token for the thanks/view pages
      // before we wipe the draft.  Without this, a refresh of the
      // thank-you page loses the resume link.
      sessionStorage.setItem(
        "t911_registration_last",
        JSON.stringify({ registration_id: regId, resume_token: token }),
      );

      // Submit immediately — the wizard captured all info, so there's
      // no value in leaving the row in "draft".
      await RegistrationAPI.submit(regId, token);

      resetDraft();
      navigate(`/register/${regId}/thanks`);
    } catch (err) {
      const msg = err?.message || "Something went wrong submitting your registration.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />

      <main className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 bg-red-600 rounded-2xl shadow-2xl mb-4 ring-4 ring-red-500/20">
              <Shield className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">Start Service with True911+</h1>
            <p className="text-slate-400 text-sm">
              {step.help}
            </p>
          </div>

          <StepIndicator stepIndex={stepIndex} />

          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8 mb-5">
            {step.key === "welcome" && <WelcomeStep />}
            {step.key === "customer" && <CustomerStep draft={draft} set={set} />}
            {step.key === "contact" && <ContactStep draft={draft} set={set} />}
            {step.key === "locations" && <LocationsStep draft={draft} setDraft={setDraft} />}
            {step.key === "units" && <ServiceUnitsStep draft={draft} setDraft={setDraft} />}
            {step.key === "device" && <DeviceStep draft={draft} set={set} />}
            {step.key === "e911" && <E911Step draft={draft} setDraft={setDraft} />}
            {step.key === "schedule" && <ScheduleStep draft={draft} set={set} />}
            {step.key === "billing" && <BillingStep draft={draft} set={set} setDraft={setDraft} />}
            {step.key === "review" && <ReviewStep draft={draft} />}
          </div>

          {error && (
            <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 mb-5 text-sm text-red-300">
              <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div>{error}</div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between gap-3">
            <button
              onClick={goBack}
              disabled={isFirst}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-slate-300 hover:text-white border border-slate-700 rounded-xl disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>

            {isLast ? (
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="inline-flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl shadow-lg shadow-red-600/20"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {submitting ? "Submitting…" : "Submit Registration"}
              </button>
            ) : (
              <button
                onClick={goNext}
                disabled={!canAdvance}
                title={canAdvance ? undefined : "Please fill the required fields to continue."}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-xl"
              >
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Need help footer */}
          <div className="mt-6 text-center text-xs text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <HelpCircle className="w-3.5 h-3.5" />
              Need help? Email{" "}
              <a href="mailto:hello@true911.com" className="text-red-400 hover:text-red-300">
                hello@true911.com
              </a>{" "}
              and our team will walk you through it.
            </span>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
