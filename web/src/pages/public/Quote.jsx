import { useState } from "react";
import { Link } from "react-router-dom";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";
import usePublicPage from "./usePublicPage";
import { Field, Honeypot, Received, SubmitButton, SubmitError, ToggleGroup, useLeadSubmission } from "./LeadForm";

// Values mirror the server allow-lists (api/app/services/acquisition_service.py).
const SERVICE_INTERESTS = [
  { value: "elevator", label: "Elevator phones" },
  { value: "fire_alarm", label: "Fire alarm communications" },
  { value: "emergency_phone", label: "Emergency phones / call stations" },
  { value: "other", label: "Other / not sure" },
];
const NEEDS = [
  { value: "copper_replacement", label: "Replace copper (POTS) lines" },
  { value: "visibility", label: "Status and visibility across locations" },
  { value: "e911_readiness", label: "E911 readiness" },
  { value: "not_sure", label: "Not sure yet" },
];

export default function Quote() {
  usePublicPage({
    title: "Request a Quote",
    description: "Tell True911 about the life-safety lines across your locations — elevator phones, fire alarm communications and emergency phones — and we'll follow up with a quote.",
    path: "/quote",
  });
  const [form, setForm] = useState({
    company: "", name: "", email: "", phone: "", num_locations: "",
    service_interests: [], needs: [], notes: "", website: "",
  });
  const { submit, loading, receipt, error, errors } = useLeadSubmission("/public/quote-request");

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  const toggle = (field) => (value) => setForm((f) => ({
    ...f, [field]: f[field].includes(value) ? f[field].filter((v) => v !== value) : [...f[field], value],
  }));

  const handleSubmit = (e) => {
    e.preventDefault();
    submit({
      ...form,
      phone: form.phone || null,
      num_locations: form.num_locations ? Number(form.num_locations) : null,
      notes: form.notes || null,
    });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />
      <main id="main" className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-10">
            <img src="/brand/true911-beacon-reversed.svg" alt="" aria-hidden="true" className="w-14 h-14 mx-auto mb-4" />
            <h1 className="text-3xl font-bold tracking-tight mb-2">Request a Quote</h1>
            <p className="text-slate-300">
              Tell us about the life-safety lines across your locations. A True911 specialist reviews every request
              and follows up — nothing is priced or purchased on this page.
            </p>
          </div>

          {receipt ? (
            <Received title="Quote request received" receipt={receipt}>
              Your request is saved in True911. A specialist will review it and contact you.
            </Received>
          ) : (
            <form onSubmit={handleSubmit} noValidate={false}
              className="relative bg-slate-800/60 border border-slate-600/60 rounded-2xl p-6 sm:p-7 space-y-6">
              <Honeypot value={form.website} onChange={set("website")} />
              <section aria-labelledby="q-contact" className="space-y-4">
                <h2 id="q-contact" className="text-sm font-semibold text-white">Contact information</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Field id="company" label="Organization" required maxLength={200} autoComplete="organization"
                    value={form.company} onChange={set("company")} error={errors.company} />
                  <Field id="name" label="Your name" required maxLength={200} autoComplete="name"
                    value={form.name} onChange={set("name")} error={errors.name} />
                  <Field id="email" label="Work email" type="email" required maxLength={254} autoComplete="email"
                    value={form.email} onChange={set("email")} error={errors.email} />
                  <Field id="phone" label="Phone" type="tel" maxLength={40} autoComplete="tel"
                    value={form.phone} onChange={set("phone")} error={errors.phone} />
                </div>
              </section>

              <section aria-labelledby="q-scope" className="space-y-4 border-t border-slate-600/50 pt-6">
                <h2 id="q-scope" className="text-sm font-semibold text-white">Your locations</h2>
                <Field id="num_locations" label="Approximate number of locations" type="number" min={1} max={100000}
                  inputMode="numeric" value={form.num_locations} onChange={set("num_locations")}
                  hint="An estimate is fine." error={errors.num_locations} />
                <ToggleGroup idPrefix="interests" label="Which life-safety lines?" hint="Select all that apply."
                  options={SERVICE_INTERESTS} selected={form.service_interests} onToggle={toggle("service_interests")} />
                <ToggleGroup idPrefix="needs" label="What do you need help with?" hint="Select all that apply."
                  options={NEEDS} selected={form.needs} onToggle={toggle("needs")} />
              </section>

              <Field id="notes" as="textarea" rows={4} label="Anything else we should know?" maxLength={4000}
                value={form.notes} onChange={set("notes")}
                hint="Timeline, carrier situation, building types — whatever is helpful." error={errors.notes} />

              <SubmitError message={error} />
              <SubmitButton loading={loading}>Send quote request</SubmitButton>
              <p className="text-center text-xs text-slate-400">
                Prefer a structured review? <Link to="/get-started" className="text-[#60A9FF] hover:text-white underline-offset-2 hover:underline">Request a Life-Safety Assessment</Link>
              </p>
            </form>
          )}
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}
