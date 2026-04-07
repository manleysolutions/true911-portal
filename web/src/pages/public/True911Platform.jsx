import { Link } from "react-router-dom";
import {
  Shield, CheckCircle, ArrowRight, Download,
  Cpu, Lock, Eye, Layers, Radio, RefreshCw,
  Phone, Settings, BarChart3, FileCheck,
  XCircle, AlertTriangle,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";

/* ── Data ───────────────────────────────────────────────────────── */

const DIFFERENTIATORS = [
  {
    icon: Cpu,
    title: "BYOD — Hardware Agnostic",
    desc: "Use any SIP-compatible device. No proprietary hardware lock-in, no forced upgrades, no single-vendor dependency.",
  },
  {
    icon: FileCheck,
    title: "Compliance-Driven Platform",
    desc: "Kari's Law, RAY BAUM's Act, and E911 requirements enforced automatically. Audit-ready documentation generated on demand.",
  },
  {
    icon: Settings,
    title: "Full Lifecycle Management",
    desc: "From provisioning through inspection — manage every device across its entire lifecycle from a single dashboard.",
  },
  {
    icon: Radio,
    title: "Emergency Reliability",
    desc: "Multi-path failover across WiFi, Ethernet, cellular, and satellite. If one path fails, traffic reroutes instantly.",
  },
  {
    icon: Eye,
    title: "Centralized Visibility",
    desc: "One portal for every site, every device, every line. Real-time status, alerts, and reporting across your entire portfolio.",
  },
];

const BENEFITS = [
  {
    icon: Shield,
    title: "Guaranteed Emergency Connectivity",
    desc: "Multi-carrier, multi-path architecture ensures your emergency phones never go dark — even during network outages.",
  },
  {
    icon: FileCheck,
    title: "Compliance Readiness",
    desc: "Automated E911 address validation, Kari's Law enforcement, and RAY BAUM's Act dispatchable location data. Always audit-ready.",
  },
  {
    icon: Lock,
    title: "Reduced Liability",
    desc: "24/7 monitoring with instant alerts means you know about failures in seconds — not after an incident. Full audit trails protect you.",
  },
  {
    icon: RefreshCw,
    title: "No Vendor Lock-In",
    desc: "Bring your own devices. Switch hardware anytime. True911 manages the connectivity and compliance layer, not the hardware.",
  },
  {
    icon: BarChart3,
    title: "Simplified Inspections",
    desc: "Automated test logs, compliance reports, and device health records. No more clipboard walk-throughs or manual documentation.",
  },
  {
    icon: Layers,
    title: "Multi-Property Visibility",
    desc: "Portfolio-wide dashboard for property managers and facilities directors. See every building, every device, one login.",
  },
];

const COMPARISON = [
  {
    feature: "Hardware Flexibility",
    true911: "Any SIP-compatible device (BYOD)",
    traditional: "Proprietary hardware required",
  },
  {
    feature: "Network Redundancy",
    true911: "4-path automatic failover",
    traditional: "Single copper line",
  },
  {
    feature: "Compliance Tracking",
    true911: "Automated, real-time",
    traditional: "Manual spreadsheets",
  },
  {
    feature: "Failure Detection",
    true911: "Instant alerts (seconds)",
    traditional: "Discovered during testing or emergencies",
  },
  {
    feature: "Device Management",
    true911: "Remote diagnostics & firmware",
    traditional: "On-site truck rolls",
  },
  {
    feature: "Portfolio Visibility",
    true911: "Single NOC dashboard",
    traditional: "Per-site, per-vendor fragmented",
  },
  {
    feature: "Vendor Lock-In",
    true911: "None — bring your own device",
    traditional: "Locked to provider hardware",
  },
  {
    feature: "Inspection Readiness",
    true911: "Auto-generated reports & logs",
    traditional: "Manual documentation",
  },
];

/* ── Component ──────────────────────────────────────────────────── */

export default function True911Platform() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <PublicNav />

      {/* ═══════════════════════════════════════════════════════════
          HERO
          ═══════════════════════════════════════════════════════════ */}
      <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900" />
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-red-600/5 rounded-full blur-3xl" />

        <div className="relative max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-red-600/10 border border-red-500/20 rounded-full px-4 py-1.5 mb-6">
            <Shield className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-400 font-medium">True911+ Platform Overview</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-6">
            Emergency Communication —
            <br />
            <span className="text-red-500">Guaranteed, Compliant, and Future-Proof</span>
          </h1>

          <p className="text-lg sm:text-xl text-slate-400 max-w-3xl mx-auto mb-10 leading-relaxed">
            True911 delivers hardware-agnostic emergency connectivity with a compliance-driven
            platform managing systems from installation through inspection. No vendor lock-in.
            No single points of failure. No compliance gaps.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="/downloads/true911-flyer.pdf"
              target="_blank"
              rel="noopener noreferrer"
              className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
            >
              <Download className="w-4 h-4" />
              Download Full Overview
            </a>
            <Link
              to="/quote"
              className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/10 flex items-center justify-center gap-2"
            >
              Talk to a Specialist <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════
          CORE DIFFERENTIATORS
          ═══════════════════════════════════════════════════════════ */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              What Makes True911 <span className="text-red-500">Different</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              Not another POTS replacement box. A complete platform for emergency communication lifecycle management.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {DIFFERENTIATORS.map((item) => (
              <div
                key={item.title}
                className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 hover:border-slate-600/50 transition-colors group"
              >
                <div className="w-10 h-10 bg-red-600/10 rounded-lg flex items-center justify-center mb-4 group-hover:bg-red-600/20 transition-colors">
                  <item.icon className="w-5 h-5 text-red-500" />
                </div>
                <h3 className="text-base font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════
          BENEFITS
          ═══════════════════════════════════════════════════════════ */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              The <span className="text-red-500">True911 Advantage</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              Outcomes that matter for the people responsible for life-safety systems.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {BENEFITS.map((item) => (
              <div
                key={item.title}
                className="flex items-start gap-4 bg-slate-800/30 border border-slate-700/40 rounded-xl p-6 hover:border-slate-600/50 transition-colors"
              >
                <div className="w-10 h-10 bg-emerald-600/10 rounded-lg flex items-center justify-center flex-shrink-0">
                  <item.icon className="w-5 h-5 text-emerald-500" />
                </div>
                <div>
                  <h3 className="text-base font-semibold mb-1">{item.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════
          COMPARISON TABLE
          ═══════════════════════════════════════════════════════════ */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              True911 vs <span className="text-red-500">Traditional Providers</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              See why facilities teams, property managers, and integrators are switching.
            </p>
          </div>

          {/* Desktop table */}
          <div className="hidden sm:block overflow-hidden rounded-xl border border-slate-700/50">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-800/80">
                  <th className="text-left text-sm font-semibold px-6 py-4 text-slate-300">Feature</th>
                  <th className="text-left text-sm font-semibold px-6 py-4 text-red-400">True911+</th>
                  <th className="text-left text-sm font-semibold px-6 py-4 text-slate-500">Traditional</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row, i) => (
                  <tr
                    key={row.feature}
                    className={i % 2 === 0 ? "bg-slate-800/30" : "bg-slate-800/10"}
                  >
                    <td className="px-6 py-3.5 text-sm font-medium text-white">{row.feature}</td>
                    <td className="px-6 py-3.5 text-sm text-emerald-400">
                      <span className="flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 flex-shrink-0" />
                        {row.true911}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-sm text-slate-500">
                      <span className="flex items-center gap-2">
                        <XCircle className="w-4 h-4 flex-shrink-0 text-slate-600" />
                        {row.traditional}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden space-y-3">
            {COMPARISON.map((row) => (
              <div key={row.feature} className="bg-slate-800/30 border border-slate-700/40 rounded-xl p-4">
                <div className="text-sm font-semibold text-white mb-2">{row.feature}</div>
                <div className="flex items-start gap-2 mb-1.5">
                  <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                  <span className="text-sm text-emerald-400">{row.true911}</span>
                </div>
                <div className="flex items-start gap-2">
                  <XCircle className="w-4 h-4 text-slate-600 mt-0.5 flex-shrink-0" />
                  <span className="text-sm text-slate-500">{row.traditional}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════
          FINAL CTA
          ═══════════════════════════════════════════════════════════ */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mx-auto text-center">
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700/50 rounded-2xl p-10 sm:p-14">
            <h2 className="text-2xl sm:text-3xl font-bold mb-4">
              Ready to See the Full Picture?
            </h2>
            <p className="text-slate-400 mb-8 max-w-xl mx-auto">
              Download our platform overview for a detailed look at how True911 replaces copper,
              enforces compliance, and gives you complete visibility across every life-safety endpoint.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a
                href="/downloads/true911-flyer.pdf"
                target="_blank"
                rel="noopener noreferrer"
                className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                Download Full Overview
              </a>
              <Link
                to="/quote"
                className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/10 flex items-center justify-center gap-2"
              >
                Talk to a Specialist <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/login"
                className="w-full sm:w-auto px-8 py-3.5 text-slate-400 hover:text-white font-medium text-sm transition-colors flex items-center justify-center gap-2"
              >
                Customer Login <ArrowRight className="w-4 h-4" />
              </Link>
            </div>

            {/* Trust badges */}
            <div className="mt-10 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-500">
              <div className="flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                <span>NDAA-TAA Compliant</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                <span>Kari's Law</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                <span>RAY BAUM's Act</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-blue-400" />
                <span className="text-blue-400 font-bold">Made in USA</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
