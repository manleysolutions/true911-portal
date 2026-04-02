import { Link } from "react-router-dom";
import {
  Shield, Radio, MapPin, AlertOctagon, Activity, Cpu,
  Phone, CheckCircle, ArrowRight, Building2, Layers,
  Globe, Zap, Lock, BarChart3, Users, AlertTriangle,
  Wifi, Signal, Satellite, RefreshCw, XCircle, Eye,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";

/* ── Data ───────────────────────────────────────────────────────── */

const BENEFITS = [
  {
    icon: Eye,
    title: "Know Immediately When a Device Fails",
    desc: "Every elevator phone, fire panel, and emergency endpoint is monitored 24/7. If a device goes offline, you know in seconds — not after someone calls 911 and nothing happens.",
  },
  {
    icon: MapPin,
    title: "Stay Compliant Without Manual Tracking",
    desc: "Automated E911 address validation, Kari's Law, and RAY BAUM's Act compliance tracking. No more spreadsheets, no more guesswork, no more audit surprises.",
  },
  {
    icon: AlertOctagon,
    title: "Respond Faster and Document Everything",
    desc: "Structured incident workflows with automatic escalation, acknowledgment tracking, and full audit trails. Every action timestamped and recorded.",
  },
  {
    icon: Activity,
    title: "See Your Entire Portfolio in One View",
    desc: "One dashboard for every site, every device, every line. Property managers and facilities directors get real-time visibility across hundreds of locations.",
  },
  {
    icon: Cpu,
    title: "Fix Issues Without Dispatching a Technician",
    desc: "Remote diagnostics, firmware updates, and configuration changes from the portal. Fewer truck rolls, faster resolution, lower cost.",
  },
  {
    icon: Phone,
    title: "Never Rely on a Single Network Again",
    desc: "Multi-carrier connectivity with automatic failover. If one path goes down, traffic reroutes instantly. No single point of failure.",
  },
];

const FAILOVER_PATHS = [
  { icon: Wifi, label: "WiFi", desc: "Primary broadband connection" },
  { icon: Globe, label: "Ethernet", desc: "Wired network backup" },
  { icon: Signal, label: "Cellular", desc: "LTE/5G failover" },
  { icon: Satellite, label: "Satellite", desc: "Last-resort connectivity" },
];

const INDUSTRIES = [
  {
    icon: Building2,
    title: "Commercial Real Estate",
    desc: "Elevator phones, fire panels, and emergency call stations across multi-tenant buildings, office parks, and mixed-use developments. Eliminate copper from your portfolio.",
  },
  {
    icon: Layers,
    title: "Healthcare & Senior Living",
    desc: "Hospitals, clinics, and assisted living facilities where a failed emergency phone is a life-safety liability. Continuous monitoring, zero blind spots.",
  },
  {
    icon: Globe,
    title: "Government & Public Sector",
    desc: "Campus safety systems, blue light phones, and emergency infrastructure with NDAA-TAA compliance built in. Procurement-ready from day one.",
  },
  {
    icon: Users,
    title: "MSPs & Integrators",
    desc: "Manage life-safety devices across your entire customer base from a single NOC. White-glove service without white-knuckle monitoring.",
  },
];

const COMPLIANCE_ITEMS = [
  { label: "NDAA-TAA Compliant", desc: "No banned components. Meets federal procurement requirements." },
  { label: "Kari's Law", desc: "Direct 911 dialing and automatic notification — verified and enforced." },
  { label: "RAY BAUM's Act", desc: "Dispatchable location data delivered with every emergency call." },
  { label: "Made in USA", desc: "Designed, built, and supported domestically." },
];

/* ── Component ──────────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <PublicNav />

      {/* ════════════════════════════════════════════════════════════
          HERO
          ════════════════════════════════════════════════════════════ */}
      <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900" />
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-red-600/5 rounded-full blur-3xl" />

        <div className="relative max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-red-600/10 border border-red-500/20 rounded-full px-4 py-1.5 mb-6">
            <AlertTriangle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-400 font-medium">Copper Lines Are Failing. Your Compliance Clock Is Ticking.</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-6">
            Your Elevator Phones Still Run
            <br />
            <span className="text-red-500">on Copper. That's a Problem.</span>
          </h1>

          <p className="text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            POTS lines are being decommissioned. Carriers are raising rates. And when a copper line
            fails silently, your emergency phones don't work — and you won't know until someone's life depends on it.
            True911 replaces copper with monitored, multi-path connectivity you can actually trust.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/quote"
              className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
            >
              Get a Quote <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/get-started"
              className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/10 flex items-center justify-center gap-2"
            >
              Start Free Audit
            </Link>
            <Link
              to="/login"
              className="w-full sm:w-auto px-8 py-3.5 text-slate-400 hover:text-white font-medium text-sm transition-colors flex items-center justify-center gap-2"
            >
              Portal Login <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

          {/* Trust badges */}
          <div className="mt-14 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-500">
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
      </section>

      {/* ════════════════════════════════════════════════════════════
          THE PROBLEM
          ════════════════════════════════════════════════════════════ */}
      <section id="problem" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Copper Is Dying. <span className="text-red-500">Your Life-Safety Lines Are at Risk.</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              This isn't a future problem. It's happening right now, in buildings across the country.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {[
              {
                icon: XCircle,
                title: "Carriers Are Abandoning POTS",
                desc: "AT&T, Verizon, and CenturyLink are actively decommissioning copper infrastructure. Rates are doubling and tripling. In many areas, you can't even order a new POTS line.",
              },
              {
                icon: AlertTriangle,
                title: "Silent Failures Kill",
                desc: "A copper line can fail with no warning. No alarm, no notification. The elevator phone looks fine — until someone pushes the button and gets silence.",
              },
              {
                icon: MapPin,
                title: "Compliance Is Getting Stricter",
                desc: "Kari's Law and RAY BAUM's Act require dispatchable location data and direct 911 dialing. Copper lines can't deliver that. Inspectors are checking.",
              },
              {
                icon: BarChart3,
                title: "Manual Testing Doesn't Scale",
                desc: "If you're testing elevator phones by riding to each floor with a clipboard, you're burning time and still missing failures between tests. There's a better way.",
              },
            ].map((item) => (
              <div
                key={item.title}
                className="bg-slate-800/40 border border-slate-700/40 rounded-xl p-6"
              >
                <div className="w-10 h-10 bg-red-600/10 rounded-lg flex items-center justify-center mb-4">
                  <item.icon className="w-5 h-5 text-red-400" />
                </div>
                <h3 className="text-base font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          THE SOLUTION
          ════════════════════════════════════════════════════════════ */}
      <section id="solution" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Replace Copper. <span className="text-red-500">Monitor Everything. Stay Compliant.</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              True911 is the managed platform that replaces your POTS lines with resilient, monitored
              connectivity — and gives you real-time visibility into every life-safety device you're responsible for.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              "Replace copper with multi-path IP connectivity that fails over automatically",
              "Monitor every elevator phone, fire panel, and emergency endpoint 24/7",
              "Enforce E911 compliance automatically — Kari's Law and RAY BAUM's Act",
              "Manage your entire portfolio from a single NOC dashboard",
              "Get alerted in seconds when any device goes offline or degrades",
              "Reduce truck rolls with remote diagnostics and firmware management",
            ].map((text, i) => (
              <div key={i} className="flex items-start gap-3 p-4 bg-slate-800/30 border border-slate-700/30 rounded-xl">
                <CheckCircle className="w-5 h-5 text-emerald-500 mt-0.5 flex-shrink-0" />
                <span className="text-sm text-slate-300 leading-relaxed">{text}</span>
              </div>
            ))}
          </div>

          <div className="mt-10 text-center">
            <Link
              to="/quote"
              className="inline-flex items-center gap-2 px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20"
            >
              Get a Quote <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          BENEFITS (outcome-driven)
          ════════════════════════════════════════════════════════════ */}
      <section id="benefits" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              What Changes When You <span className="text-red-500">Switch to True911</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              Not features. Outcomes. Here's what your day-to-day actually looks like.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {BENEFITS.map((item) => (
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

      {/* ════════════════════════════════════════════════════════════
          FAILOVER / RELIABILITY
          ════════════════════════════════════════════════════════════ */}
      <section id="failover" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Four Paths. <span className="text-red-500">Zero Single Points of Failure.</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              Copper gives you one path. When it fails, you're dark. True911 devices connect
              through up to four independent paths and fail over automatically — no human intervention required.
            </p>
          </div>

          {/* Failover path diagram */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
            {FAILOVER_PATHS.map((path, i) => (
              <div key={path.label} className="relative">
                <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-5 text-center hover:border-red-500/30 transition-colors">
                  <div className="w-12 h-12 bg-red-600/10 rounded-full flex items-center justify-center mx-auto mb-3">
                    <path.icon className="w-6 h-6 text-red-400" />
                  </div>
                  <div className="text-sm font-semibold mb-0.5">{path.label}</div>
                  <div className="text-xs text-slate-500">{path.desc}</div>
                  <div className="mt-2">
                    <span className="inline-block text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-slate-700/50 px-2 py-0.5 rounded-full">
                      Path {i + 1}
                    </span>
                  </div>
                </div>
                {/* Arrow between cards */}
                {i < 3 && (
                  <div className="hidden sm:flex absolute top-1/2 -right-2.5 -translate-y-1/2 z-10">
                    <RefreshCw className="w-4 h-4 text-slate-600" />
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-6 text-center">
            <p className="text-sm text-slate-300 leading-relaxed max-w-2xl mx-auto">
              If WiFi drops, traffic moves to Ethernet. If Ethernet fails, cellular takes over.
              If cellular goes down, satellite keeps the connection alive. Every failover is automatic,
              every transition is logged, and you're notified the moment any path degrades.
              <span className="text-red-400 font-medium"> Your emergency phones stay online. Period.</span>
            </p>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          INDUSTRIES
          ════════════════════════════════════════════════════════════ */}
      <section id="industries" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Built for the People <span className="text-red-500">Responsible for Safety</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              Property managers, facilities directors, and integrators who can't afford a gap in life-safety coverage.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {INDUSTRIES.map((ind) => (
              <div
                key={ind.title}
                className="flex items-start gap-4 bg-slate-800/30 border border-slate-700/40 rounded-xl p-6 hover:border-slate-600/50 transition-colors"
              >
                <div className="w-12 h-12 bg-slate-700/50 rounded-lg flex items-center justify-center flex-shrink-0">
                  <ind.icon className="w-6 h-6 text-red-400" />
                </div>
                <div>
                  <h3 className="text-base font-semibold mb-1">{ind.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{ind.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          TRUST / COMPLIANCE
          ════════════════════════════════════════════════════════════ */}
      <section id="compliance" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Procurement-Ready. <span className="text-red-500">Inspection-Proof.</span>
            </h2>
            <p className="text-slate-400 max-w-xl mx-auto">
              True911 is built to pass the audits your current setup can't.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {COMPLIANCE_ITEMS.map((item) => (
              <div key={item.label} className="flex items-start gap-3 p-5 bg-slate-800/30 border border-slate-700/30 rounded-xl">
                <CheckCircle className="w-5 h-5 text-emerald-500 mt-0.5 flex-shrink-0" />
                <div>
                  <div className="text-sm font-semibold mb-0.5">{item.label}</div>
                  <div className="text-xs text-slate-400">{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════
          FINAL CTA
          ════════════════════════════════════════════════════════════ */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-3xl mx-auto text-center">
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700/50 rounded-2xl p-10 sm:p-14">
            <h2 className="text-2xl sm:text-3xl font-bold mb-4">
              Stop Paying More for Lines That Don't Work.
            </h2>
            <p className="text-slate-400 mb-8 max-w-xl mx-auto">
              Get a custom quote to replace your copper lines, or let us audit your current life-safety
              infrastructure for free. Either way, you'll know exactly where you stand.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                to="/quote"
                className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
              >
                Get a Quote <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/get-started"
                className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/10 flex items-center justify-center gap-2"
              >
                Start Free Audit
              </Link>
              <Link
                to="/login"
                className="w-full sm:w-auto px-8 py-3.5 text-slate-400 hover:text-white font-medium text-sm transition-colors flex items-center justify-center gap-2"
              >
                Customer Login <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
