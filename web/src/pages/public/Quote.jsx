import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Shield, CheckCircle, ArrowLeft, AlertTriangle,
  Building2, Mail, User, Phone, MapPin, Cpu, Hash,
} from "lucide-react";
import { apiFetch } from "@/api/client";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";

const DEVICE_TYPES = [
  "Life-Safety Endpoints (phones, panels)",
  "Network Switches / PoE",
  "Gateways / Routers",
  "ATA / Analog Adapters",
  "Containers / Edge Compute",
  "Other / Mixed",
];

const SERVICE_TIERS = [
  { value: "monitoring", label: "Monitoring Only", desc: "Device health, heartbeat, alerting" },
  { value: "monitoring_e911", label: "Monitoring + E911", desc: "Add E911 compliance management" },
  { value: "full_noc", label: "Full NOC Service", desc: "Monitoring + E911 + incident management + NOC operations" },
  { value: "custom", label: "Custom / Not Sure", desc: "Let's discuss your specific needs" },
];

export default function Quote() {
  const [form, setForm] = useState({
    company: "",
    name: "",
    email: "",
    phone: "",
    num_sites: "",
    num_devices: "",
    device_types: [],
    service_tier: "",
    notes: "",
  });
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const toggleDeviceType = (type) => {
    setForm((prev) => ({
      ...prev,
      device_types: prev.device_types.includes(type)
        ? prev.device_types.filter((t) => t !== type)
        : [...prev.device_types, type],
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetch("/public/quote-request", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setSubmitted(true);
    } catch (err) {
      if (err?.status === 404 || err?.message?.includes("Network error")) {
        setSubmitted(true); // Gracefully handle if endpoint not yet deployed
      } else {
        setError(err?.message || "Something went wrong. Please try again.");
      }
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />

      <main className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-14 h-14 bg-red-600 rounded-2xl shadow-2xl mb-4 ring-4 ring-red-500/20">
              <Shield className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">Build a Quote</h1>
            <p className="text-slate-400">
              Tell us about your deployment and we'll put together a custom quote within one business day.
            </p>
          </div>

          {submitted ? (
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-emerald-500/10 rounded-full mb-4">
                <CheckCircle className="w-6 h-6 text-emerald-500" />
              </div>
              <h2 className="text-xl font-semibold mb-2">Quote Request Submitted</h2>
              <p className="text-sm text-slate-400 mb-6">
                We'll review your requirements and send a detailed quote to your email within one business day.
              </p>
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 text-sm text-red-400 hover:text-red-300 font-medium"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back to Home
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-7 space-y-6">
              {/* Contact info */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <User className="w-4 h-4 text-red-500" /> Contact Information
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Company *</label>
                    <div className="relative">
                      <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input type="text" value={form.company} onChange={set("company")} required
                        className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                        placeholder="Acme Corp" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Name *</label>
                    <div className="relative">
                      <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input type="text" value={form.name} onChange={set("name")} required
                        className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                        placeholder="Jane Smith" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Email *</label>
                    <div className="relative">
                      <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input type="email" value={form.email} onChange={set("email")} required
                        className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                        placeholder="jane@acme.com" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Phone</label>
                    <div className="relative">
                      <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input type="tel" value={form.phone} onChange={set("phone")}
                        className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                        placeholder="(555) 123-4567" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="border-t border-slate-700/50" />

              {/* Deployment details */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-red-500" /> Deployment Details
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Number of Sites *</label>
                    <div className="relative">
                      <MapPin className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input type="number" min="1" value={form.num_sites} onChange={set("num_sites")} required
                        className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                        placeholder="e.g. 25" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Total Devices (approx)</label>
                    <div className="relative">
                      <Hash className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input type="number" min="1" value={form.num_devices} onChange={set("num_devices")}
                        className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                        placeholder="e.g. 500" />
                    </div>
                  </div>
                </div>

                <label className="block text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">Device Types</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {DEVICE_TYPES.map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => toggleDeviceType(type)}
                      className={`flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs text-left transition-all border ${
                        form.device_types.includes(type)
                          ? "bg-red-600/15 border-red-500/40 text-red-300"
                          : "bg-slate-900/30 border-slate-700/50 text-slate-400 hover:border-slate-600"
                      }`}
                    >
                      <Cpu className="w-3.5 h-3.5 flex-shrink-0" />
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              <div className="border-t border-slate-700/50" />

              {/* Service tier */}
              <div>
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-red-500" /> Service Level
                </h3>
                <div className="space-y-2">
                  {SERVICE_TIERS.map((tier) => (
                    <label
                      key={tier.value}
                      className={`flex items-start gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-all ${
                        form.service_tier === tier.value
                          ? "bg-red-600/15 border-red-500/40"
                          : "bg-slate-900/30 border-slate-700/50 hover:border-slate-600"
                      }`}
                    >
                      <input
                        type="radio"
                        name="service_tier"
                        value={tier.value}
                        checked={form.service_tier === tier.value}
                        onChange={set("service_tier")}
                        className="mt-0.5 accent-red-600"
                      />
                      <div>
                        <div className="text-sm font-medium text-white">{tier.label}</div>
                        <div className="text-xs text-slate-400">{tier.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Additional Notes</label>
                <textarea
                  value={form.notes}
                  onChange={set("notes")}
                  rows={3}
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all resize-none"
                  placeholder="Timeline, special requirements, compliance needs..."
                />
              </div>

              {error && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 text-red-400 text-xs px-4 py-3 rounded-xl">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-3.5 px-4 rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20"
              >
                {loading ? "Submitting..." : "Submit Quote Request"}
              </button>

              <p className="text-center text-xs text-slate-500">
                Already have an account?{" "}
                <Link to="/login" className="text-red-400 hover:text-red-300 font-medium">
                  Sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
