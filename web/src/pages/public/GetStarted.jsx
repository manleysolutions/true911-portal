import { useState } from "react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";
import usePublicPage from "./usePublicPage";
import { Field, Honeypot, Received, SubmitButton, SubmitError, useLeadSubmission } from "./LeadForm";

const ROLES = ["Facilities / property management", "IT / telecom", "Operations / risk", "Procurement",
  "Integrator / MSP", "Other"];

// Request a Life-Safety Assessment (D-032).  This page starts the conversation;
// the assessment itself is done with a True911 specialist — it is not an
// automated audit, and nothing here verifies E911 or compliance.
export default function GetStarted() {
  usePublicPage({
    title: "Request a Life-Safety Assessment",
    description: "Start a Life-Safety Assessment with True911: a specialist reviews the elevator phones, fire alarm communications and emergency phones across your locations.",
    path: "/get-started",
  });
  const [form, setForm] = useState({ company: "", name: "", email: "", phone: "", role: "", message: "", website: "" });
  const { submit, loading, receipt, error, errors } = useLeadSubmission("/public/request-access");
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    submit({ ...form, phone: form.phone || null, role: form.role || null, message: form.message || null });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />
      <main id="main" className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-xl mx-auto">
          <div className="text-center mb-10">
            <img src="/brand/true911-beacon-reversed.svg" alt="" aria-hidden="true" className="w-14 h-14 mx-auto mb-4" />
            <h1 className="text-3xl font-bold tracking-tight mb-2">Request a Life-Safety Assessment</h1>
            <p className="text-slate-300">
              Tell us about your portfolio. A True911 specialist will review the life-safety lines across your
              locations with you and recommend next steps.
            </p>
          </div>

          {receipt ? (
            <Received title="Assessment request received" receipt={receipt}>
              Your request is saved in True911. A specialist will contact you to schedule the assessment.
            </Received>
          ) : (
            <form onSubmit={handleSubmit}
              className="relative bg-slate-800/60 border border-slate-600/60 rounded-2xl p-6 sm:p-7 space-y-5">
              <Honeypot value={form.website} onChange={set("website")} />
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
              <Field id="role" as="select" label="Your role" value={form.role} onChange={set("role")} error={errors.role}>
                <option value="">Select…</option>
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </Field>
              <Field id="message" as="textarea" rows={4} label="About your locations" maxLength={4000}
                value={form.message} onChange={set("message")}
                hint="Roughly how many locations, which lines (elevator, fire alarm, emergency phones), and your timeline."
                error={errors.message} />
              <SubmitError message={error} />
              <SubmitButton loading={loading}>Request a Life-Safety Assessment</SubmitButton>
            </form>
          )}
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}
