import { Link } from "react-router-dom";
import {
  MapPin, AlertOctagon, Activity, Cpu, CheckCircle, ArrowRight, Building2, Layers,
  Globe, Users, AlertTriangle, XCircle, Eye, BarChart3, Wrench, Radio,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";
import usePublicPage from "./usePublicPage";
import { rememberCta } from "@/lib/acquisition";

// Public claims inherit the platform truth rules (D-030): no guaranteed
// connectivity, no "instant" alerts, no automated compliance, no universal
// failover, no blanket origin/procurement claims.  Brand blue for action; red
// only for risk (D-033).  Structure kept — the full redesign is a later PR.

const BENEFITS = [
  { icon: Eye, title: "Status across every location",
    desc: "One view of the elevator phones, fire alarm communicators and emergency phones True911 monitors for you. When status can't be confirmed, it's shown as unknown — never as healthy." },
  { icon: AlertOctagon, title: "Find failures sooner than manual testing",
    desc: "Monitored devices report in on a schedule. When one stops reporting or degrades, your team is alerted instead of waiting for the next walk-through test." },
  { icon: MapPin, title: "Location records you can act on",
    desc: "Keep the address and location details for each line in one place, with what's been confirmed kept clearly separate from what's only on file." },
  { icon: Activity, title: "Documented incident handling",
    desc: "Incidents are tracked with acknowledgement and a timestamped history, so you can see what happened and who responded." },
  { icon: Cpu, title: "Remote diagnostics where supported",
    desc: "On supported equipment, many issues can be investigated and resolved remotely — fewer truck rolls and faster answers." },
  { icon: Wrench, title: "Operated by True911",
    desc: "True911 plans, deploys and operates the service with you. You get a partner accountable for the life-safety lines — not another box to manage." },
];

const INDUSTRIES = [
  { icon: Building2, title: "Multi-location portfolios",
    desc: "Retail chains, enterprise real estate and property-management portfolios with elevator phones, fire alarm lines and emergency phones spread across dozens or hundreds of sites." },
  { icon: Globe, title: "Public sector & campuses",
    desc: "Campus emergency phones, call stations and building life-safety lines across facilities managed by one team." },
  { icon: Layers, title: "Healthcare & senior living",
    desc: "Facilities where an emergency phone that quietly stops working is a real risk to residents, patients and staff." },
  { icon: Users, title: "Channel partners & MSPs",
    desc: "Integrators and managed-service providers who support life-safety communications for many customers." },
];

function Cta({ to, cta, primary, children }) {
  return (
    <Link to={to} onClick={() => rememberCta(cta)}
      className={primary
        ? "w-full sm:w-auto min-h-[48px] px-8 py-3.5 bg-[#1C6FE6] hover:bg-[#12408F] text-white font-semibold rounded-xl transition-colors text-sm shadow-lg shadow-[#1C6FE6]/20 flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF]"
        : "w-full sm:w-auto min-h-[48px] px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/15 flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF]"}>
      {children}
    </Link>
  );
}

export default function LandingPage() {
  usePublicPage({
    title: "True911 — The Operating System for Life-Safety Communications",
    description: "True911 helps multi-location organizations replace aging copper lines and see the status of elevator phones, fire alarm communications and emergency phones across every location.",
    path: "/",
  });
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <PublicNav />

      {/* HERO */}
      <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0B1F3B] via-slate-950 to-slate-900" />
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-[#2D8CFF]/10 rounded-full blur-3xl" />
        <div className="relative max-w-5xl mx-auto text-center">
          <p className="inline-flex items-center gap-2 bg-[#2D8CFF]/10 border border-[#60A9FF]/30 rounded-full px-4 py-1.5 mb-6 text-sm text-[#9CC8FF] font-medium">
            <Radio className="w-4 h-4" aria-hidden="true" /> Elevator phones · Fire alarm communications · Emergency phones
          </p>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-6">
            The Operating System for
            <br />
            <span className="text-[#60A9FF]">Life-Safety Communications</span>
          </h1>
          <p className="text-lg sm:text-xl text-slate-300 max-w-2xl mx-auto mb-10 leading-relaxed">
            Copper phone lines are being retired, and the life-safety lines that depend on them are easy to lose
            track of. True911 replaces aging lines with a managed service and gives your team one place to see
            what&apos;s installed, what&apos;s reporting and what needs attention — across every location.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Cta to="/get-started" cta="hero_assessment" primary>
              Start a Life-Safety Assessment <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Cta>
            <Cta to="/quote" cta="hero_quote">Request a quote</Cta>
          </div>
        </div>
      </section>

      {/* THE PROBLEM — risk framing is the one place red is used */}
      <section id="problem" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Copper is being retired. <span className="text-red-400">Life-safety lines are exposed.</span>
            </h2>
            <p className="text-slate-300 max-w-2xl mx-auto">
              Most organizations can&apos;t say with confidence how many of these lines they have, where they are,
              or whether they work today.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {[
              { icon: XCircle, title: "Carriers are retiring POTS",
                desc: "Major carriers are winding down copper networks. In many areas POTS lines are getting more expensive, slower to repair, or unavailable to order." },
              { icon: AlertTriangle, title: "Failures can be silent",
                desc: "A copper line can stop working without any alarm. The elevator phone looks fine until someone presses the button." },
              { icon: MapPin, title: "Rules depend on accurate records",
                desc: "Federal rules such as Kari's Law and RAY BAUM'S Act address direct 911 dialing, notification and dispatchable location for many multi-line telephone systems. Meeting them starts with knowing what's installed where." },
              { icon: BarChart3, title: "Manual testing doesn't scale",
                desc: "Walk-through tests with a clipboard take time across many sites and still miss failures that happen between tests." },
            ].map((item) => (
              <div key={item.title} className="bg-slate-800/40 border border-slate-700/40 rounded-xl p-6">
                <div className="w-10 h-10 bg-red-600/10 rounded-lg flex items-center justify-center mb-4">
                  <item.icon className="w-5 h-5 text-red-400" aria-hidden="true" />
                </div>
                <h3 className="text-base font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-slate-300 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* THE SOLUTION */}
      <section id="solution" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Assess. Replace. <span className="text-[#60A9FF]">Operate with visibility.</span>
            </h2>
            <p className="text-slate-300 max-w-2xl mx-auto">
              True911 starts with a Life-Safety Assessment of your locations, then deploys and operates a managed
              replacement for the lines that need it.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              "An assessment of the life-safety lines across your locations",
              "Managed replacement of copper lines, designed per location",
              "Monitoring of the devices True911 deploys or integrates",
              "Alerts when a monitored device stops reporting or degrades",
              "One portfolio view of status, locations and open issues",
              "Location and address records kept with each line",
            ].map((text) => (
              <div key={text} className="flex items-start gap-3 p-4 bg-slate-800/30 border border-slate-700/30 rounded-xl">
                <CheckCircle className="w-5 h-5 text-[#60A9FF] mt-0.5 flex-shrink-0" aria-hidden="true" />
                <span className="text-sm text-slate-200 leading-relaxed">{text}</span>
              </div>
            ))}
          </div>
          <div className="mt-10 flex justify-center">
            <Cta to="/get-started" cta="solution_assessment" primary>
              Start a Life-Safety Assessment <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Cta>
          </div>
        </div>
      </section>

      {/* BENEFITS */}
      <section id="benefits" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">What changes with True911</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {BENEFITS.map((item) => (
              <div key={item.title} className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
                <div className="w-10 h-10 bg-[#2D8CFF]/10 rounded-lg flex items-center justify-center mb-4">
                  <item.icon className="w-5 h-5 text-[#60A9FF]" aria-hidden="true" />
                </div>
                <h3 className="text-base font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-slate-300 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CONNECTIVITY — designed per location, never a universal promise */}
      <section id="connectivity" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">Connectivity designed for each location</h2>
          <p className="text-slate-300 max-w-2xl mx-auto leading-relaxed">
            Every building is different. During the assessment, True911 recommends the connectivity for each
            location based on its equipment and site conditions — commonly cellular, with additional paths where
            the site and equipment support them. What&apos;s available varies by location, and the design is
            reviewed with you before deployment.
          </p>
        </div>
      </section>

      {/* WHO IT'S FOR */}
      <section id="industries" className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Built for teams responsible for many locations</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {INDUSTRIES.map((ind) => (
              <div key={ind.title} className="flex items-start gap-4 bg-slate-800/30 border border-slate-700/40 rounded-xl p-6">
                <div className="w-12 h-12 bg-slate-700/50 rounded-lg flex items-center justify-center flex-shrink-0">
                  <ind.icon className="w-6 h-6 text-[#60A9FF]" aria-hidden="true" />
                </div>
                <div>
                  <h3 className="text-base font-semibold mb-1">{ind.title}</h3>
                  <p className="text-sm text-slate-300 leading-relaxed">{ind.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* REGULATORY CONTEXT — neutral, never a compliance determination */}
      <section id="compliance" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-10">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Regulatory context</h2>
            <p className="text-slate-300 max-w-2xl mx-auto">
              These federal rules shape how many organizations think about emergency calling.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { label: "Kari's Law", desc: "Addresses direct 911 dialing and on-site notification for many multi-line telephone systems." },
              { label: "RAY BAUM'S Act", desc: "Addresses dispatchable location information sent with 911 calls." },
            ].map((item) => (
              <div key={item.label} className="p-5 bg-slate-800/30 border border-slate-700/30 rounded-xl">
                <div className="text-sm font-semibold mb-1">{item.label}</div>
                <div className="text-sm text-slate-300">{item.desc}</div>
              </div>
            ))}
          </div>
          <p className="mt-6 text-xs text-slate-400 text-center max-w-2xl mx-auto">
            True911 helps you organize the location and device information these rules depend on. It does not
            certify compliance; how the rules apply to your systems is a determination for you and your advisors.
          </p>
        </div>
      </section>

      {/* FINAL CTA — no login here; login lives in the header */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-3xl mx-auto text-center">
          <div className="bg-gradient-to-br from-[#0B1F3B] to-slate-900 border border-slate-700/50 rounded-2xl p-10 sm:p-14">
            <h2 className="text-2xl sm:text-3xl font-bold mb-4">Know where every life-safety line stands.</h2>
            <p className="text-slate-300 mb-8 max-w-xl mx-auto">
              Start with a Life-Safety Assessment: a True911 specialist reviews your locations with you and
              recommends next steps. Prefer to start with numbers? Request a quote.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Cta to="/get-started" cta="final_assessment" primary>
                Start a Life-Safety Assessment <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </Cta>
              <Cta to="/quote" cta="final_quote">Request a quote</Cta>
            </div>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
