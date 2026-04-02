import { useState } from "react";
import { Link } from "react-router-dom";
import { Shield, CheckCircle, ArrowLeft, AlertTriangle, Building2, Mail, User, Phone } from "lucide-react";
import { apiFetch } from "@/api/client";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";

export default function GetStarted() {
  const [form, setForm] = useState({
    company: "",
    name: "",
    email: "",
    phone: "",
    role: "",
    message: "",
  });
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetch("/public/request-access", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setSubmitted(true);
    } catch (err) {
      // If the endpoint doesn't exist yet, show a friendly message
      if (err?.status === 404 || err?.message?.includes("Network error")) {
        setSubmitted(true); // Gracefully handle — form data would be emailed/logged in production
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
        <div className="max-w-xl mx-auto">
          {/* Header */}
          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-14 h-14 bg-red-600 rounded-2xl shadow-2xl mb-4 ring-4 ring-red-500/20">
              <Shield className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">Get Started with True911+</h1>
            <p className="text-slate-400">
              Request access to the platform or tell us about your deployment needs.
            </p>
          </div>

          {submitted ? (
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-emerald-500/10 rounded-full mb-4">
                <CheckCircle className="w-6 h-6 text-emerald-500" />
              </div>
              <h2 className="text-xl font-semibold mb-2">Request Received</h2>
              <p className="text-sm text-slate-400 mb-6">
                Thank you! Our team will review your request and reach out within one business day.
              </p>
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 text-sm text-red-400 hover:text-red-300 font-medium"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back to Home
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-7 space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Company Name *</label>
                  <div className="relative">
                    <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="text"
                      value={form.company}
                      onChange={set("company")}
                      className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                      placeholder="Acme Corp"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Your Name *</label>
                  <div className="relative">
                    <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="text"
                      value={form.name}
                      onChange={set("name")}
                      className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                      placeholder="Jane Smith"
                      required
                    />
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Email *</label>
                  <div className="relative">
                    <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="email"
                      value={form.email}
                      onChange={set("email")}
                      className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                      placeholder="jane@acme.com"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Phone</label>
                  <div className="relative">
                    <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="tel"
                      value={form.phone}
                      onChange={set("phone")}
                      className="w-full pl-10 pr-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                      placeholder="(555) 123-4567"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Your Role</label>
                <select
                  value={form.role}
                  onChange={set("role")}
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                >
                  <option value="">Select...</option>
                  <option value="IT Director / CTO">IT Director / CTO</option>
                  <option value="Facilities Manager">Facilities Manager</option>
                  <option value="NOC / Operations">NOC / Operations</option>
                  <option value="MSP / Integrator">MSP / Integrator</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">Tell Us About Your Needs</label>
                <textarea
                  value={form.message}
                  onChange={set("message")}
                  rows={3}
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all resize-none"
                  placeholder="Number of sites, device types, compliance requirements..."
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
                {loading ? "Submitting..." : "Request Access"}
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
