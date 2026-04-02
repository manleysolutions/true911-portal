import { Link } from "react-router-dom";
import {
  Shield, Radio, MapPin, AlertOctagon, Activity, Cpu,
  Phone, CheckCircle, ArrowRight, Building2, Layers,
  Globe, Zap, Lock, BarChart3, Users,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";

const SERVICES = [
  {
    icon: Radio,
    title: "24/7 Device Monitoring",
    desc: "Real-time heartbeat monitoring across all life-safety devices. Instant alerts when devices go offline, degrade, or fail health checks.",
  },
  {
    icon: MapPin,
    title: "E911 Compliance",
    desc: "Automated E911 address validation and compliance tracking for Kari's Law, RAY BAUM's Act, and FCC regulations.",
  },
  {
    icon: AlertOctagon,
    title: "Incident Management",
    desc: "Structured incident workflows with escalation policies, acknowledgment tracking, and resolution SLA monitoring.",
  },
  {
    icon: Activity,
    title: "NOC Command Center",
    desc: "Unified operations dashboard for your NOC team — site health, device status, active incidents, and deployment tracking in one view.",
  },
  {
    icon: Cpu,
    title: "Remote Device Management",
    desc: "Firmware updates, container management, configuration changes, and remote diagnostics — all from the portal.",
  },
  {
    icon: Phone,
    title: "Carrier & SIM Management",
    desc: "Multi-carrier SIM lifecycle management with activation, suspension, and usage monitoring across your fleet.",
  },
];

const INDUSTRIES = [
  {
    icon: Building2,
    title: "Commercial Real Estate",
    desc: "Multi-tenant buildings, office parks, and mixed-use developments with complex E911 requirements.",
  },
  {
    icon: Layers,
    title: "Healthcare & Senior Living",
    desc: "Hospitals, clinics, and assisted living facilities where life-safety uptime is non-negotiable.",
  },
  {
    icon: Globe,
    title: "Enterprise & Campus",
    desc: "Large campuses with hundreds of endpoints across multiple buildings and floors.",
  },
  {
    icon: Users,
    title: "Managed Service Providers",
    desc: "MSPs and integrators managing life-safety devices across multiple customer sites.",
  },
];

const WHY_ITEMS = [
  {
    icon: Shield,
    title: "NDAA-TAA Compliant",
    desc: "All hardware and software meets federal procurement requirements. No banned components.",
  },
  {
    icon: Lock,
    title: "Enterprise Security",
    desc: "JWT-based auth, role-based access control, audit logging, and encrypted communications.",
  },
  {
    icon: Zap,
    title: "Rapid Deployment",
    desc: "Go from zero to monitoring in hours, not weeks. Bulk import, auto-provisioning, and guided workflows.",
  },
  {
    icon: BarChart3,
    title: "Actionable Analytics",
    desc: "Device health trends, uptime SLAs, incident analytics, and compliance reporting out of the box.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <PublicNav />

      {/* ── Hero ── */}
      <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900" />
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-red-600/5 rounded-full blur-3xl" />

        <div className="relative max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-red-600/10 border border-red-500/20 rounded-full px-4 py-1.5 mb-6">
            <Shield className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-400 font-medium">Life-Safety Monitoring Platform</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-6">
            Mission-Critical Device
            <br />
            <span className="text-red-500">Monitoring & Compliance</span>
          </h1>

          <p className="text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            True911+ is the NOC platform built for life-safety. Monitor every device,
            enforce E911 compliance, and manage incidents — all from a single pane of glass.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/quote"
              className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
            >
              Build a Quote <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/get-started"
              className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/10 flex items-center justify-center gap-2"
            >
              Get Started
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
              <span>Kari's Law Ready</span>
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

      {/* ── Services ── */}
      <section id="services" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Everything You Need for <span className="text-red-500">Life-Safety Operations</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              From device health monitoring to regulatory compliance, True911+ covers the full lifecycle of life-safety device management.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {SERVICES.map((svc) => (
              <div
                key={svc.title}
                className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 hover:border-slate-600/50 transition-colors group"
              >
                <div className="w-10 h-10 bg-red-600/10 rounded-lg flex items-center justify-center mb-4 group-hover:bg-red-600/20 transition-colors">
                  <svc.icon className="w-5 h-5 text-red-500" />
                </div>
                <h3 className="text-base font-semibold mb-2">{svc.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{svc.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Industries ── */}
      <section id="industries" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Built for <span className="text-red-500">Your Industry</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              True911+ serves organizations where device uptime and E911 compliance directly impact safety.
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

      {/* ── Why True911 ── */}
      <section id="why" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Why <span className="text-red-500">True911+</span>
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              Purpose-built for life-safety, not adapted from generic IT monitoring.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {WHY_ITEMS.map((item) => (
              <div
                key={item.title}
                className="flex items-start gap-4 p-6"
              >
                <div className="w-10 h-10 bg-red-600/10 rounded-lg flex items-center justify-center flex-shrink-0">
                  <item.icon className="w-5 h-5 text-red-500" />
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

      {/* ── CTA ── */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mx-auto text-center">
          <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700/50 rounded-2xl p-10 sm:p-14">
            <h2 className="text-2xl sm:text-3xl font-bold mb-4">
              Ready to Secure Your Life-Safety Infrastructure?
            </h2>
            <p className="text-slate-400 mb-8 max-w-xl mx-auto">
              Get a custom quote for your deployment or request access to the True911+ platform today.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                to="/quote"
                className="w-full sm:w-auto px-8 py-3.5 bg-red-600 hover:bg-red-700 text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
              >
                Build a Quote <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/get-started"
                className="w-full sm:w-auto px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/10 flex items-center justify-center gap-2"
              >
                Request Access
              </Link>
            </div>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
