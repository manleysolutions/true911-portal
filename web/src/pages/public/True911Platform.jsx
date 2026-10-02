import { Link } from "react-router-dom";
import {
  ArrowRight, Cpu, Eye, Layers, Radio, Settings, ClipboardCheck, Wrench, Activity,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";
import usePublicPage from "./usePublicPage";
import { rememberCta } from "@/lib/acquisition";

// Platform overview.  Claims inherit the truth rules (D-030); the previous
// comparison table, "guaranteed" connectivity, automated-compliance and
// download-flyer CTAs (the PDF never existed) were removed.

const CAPABILITIES = [
  { icon: Eye, title: "Portfolio visibility",
    desc: "One portal for the life-safety lines across your locations: what's installed, what's reporting and what needs attention. Unknown status is shown as unknown." },
  { icon: Cpu, title: "Hardware-flexible",
    desc: "True911 works with a range of supported devices and carriers, and reads health through vendor-specific adapters — so your portfolio isn't tied to a single box." },
  { icon: Activity, title: "Monitoring and alerts",
    desc: "Devices True911 deploys or integrates report in on a schedule; when one stops reporting or degrades, your team is alerted." },
  { icon: Radio, title: "Connectivity designed per location",
    desc: "Connectivity is recommended for each location based on its equipment and site conditions — commonly cellular, with additional paths where supported." },
  { icon: Settings, title: "Lifecycle management",
    desc: "From assessment and installation through ongoing operation, each line's history stays with the location it serves." },
  { icon: Layers, title: "Location records",
    desc: "Address and location details are kept with each line, with confirmed information clearly separated from information that's only on file." },
];

const STEPS = [
  { icon: ClipboardCheck, title: "1. Assess", desc: "Start a Life-Safety Assessment. Tell us about your locations; a True911 specialist reviews the life-safety lines with you." },
  { icon: Settings, title: "2. Design", desc: "True911 recommends a replacement and connectivity design for each location and confirms scope with you." },
  { icon: Wrench, title: "3. Deploy & operate", desc: "True911 deploys and operates the service, and your team gets ongoing visibility in the portal." },
];

export default function True911Platform() {
  usePublicPage({
    title: "Platform Overview",
    description: "How True911 assesses, replaces and operates the life-safety communications — elevator phones, fire alarm communications and emergency phones — across multi-location portfolios.",
    path: "/true911-platform",
  });
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <PublicNav />

      <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0B1F3B] via-slate-950 to-slate-900" />
        <div className="relative max-w-5xl mx-auto text-center">
          <p className="inline-flex items-center gap-2 bg-[#2D8CFF]/10 border border-[#60A9FF]/30 rounded-full px-4 py-1.5 mb-6 text-sm text-[#9CC8FF] font-medium">
            Platform overview
          </p>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight mb-6">
            One platform for
            <br />
            <span className="text-[#60A9FF]">life-safety communications</span>
          </h1>
          <p className="text-lg sm:text-xl text-slate-300 max-w-3xl mx-auto mb-10 leading-relaxed">
            True911 replaces aging copper lines with a managed service and gives multi-location teams one place
            to see and manage the elevator phones, fire alarm communications and emergency phones they&apos;re
            responsible for.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/get-started" onClick={() => rememberCta("platform_hero_assessment")}
              className="w-full sm:w-auto min-h-[48px] px-8 py-3.5 bg-[#1C6FE6] hover:bg-[#12408F] text-white font-semibold rounded-xl transition-colors text-sm flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF]">
              Start a Life-Safety Assessment <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Link>
            <Link to="/quote" onClick={() => rememberCta("platform_hero_quote")}
              className="w-full sm:w-auto min-h-[48px] px-8 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-colors text-sm border border-white/15 flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF]">
              Request a quote
            </Link>
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl sm:text-4xl font-bold mb-14 text-center">What the platform does</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {CAPABILITIES.map((item) => (
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

      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl sm:text-4xl font-bold mb-14 text-center">How it works</h2>
          <ol className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {STEPS.map((s) => (
              <li key={s.title} className="bg-slate-800/30 border border-slate-700/40 rounded-xl p-6">
                <s.icon className="w-6 h-6 text-[#60A9FF] mb-3" aria-hidden="true" />
                <h3 className="text-base font-semibold mb-1">{s.title}</h3>
                <p className="text-sm text-slate-300 leading-relaxed">{s.desc}</p>
              </li>
            ))}
          </ol>
          <p className="mt-8 text-xs text-slate-400 text-center max-w-2xl mx-auto">
            True911 helps you organize the location and device information that rules such as Kari&apos;s Law and
            RAY BAUM&apos;S Act depend on. It does not certify compliance; how those rules apply to your systems is a
            determination for you and your advisors.
          </p>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-slate-900/50">
        <div className="max-w-3xl mx-auto text-center">
          <div className="bg-gradient-to-br from-[#0B1F3B] to-slate-900 border border-slate-700/50 rounded-2xl p-10 sm:p-14">
            <h2 className="text-2xl sm:text-3xl font-bold mb-4">See where your locations stand</h2>
            <p className="text-slate-300 mb-8 max-w-xl mx-auto">
              A Life-Safety Assessment is the starting point: a specialist reviews your locations with you and
              recommends next steps.
            </p>
            <Link to="/get-started" onClick={() => rememberCta("platform_final_assessment")}
              className="inline-flex min-h-[48px] px-8 py-3.5 bg-[#1C6FE6] hover:bg-[#12408F] text-white font-semibold rounded-xl transition-colors text-sm items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF]">
              Start a Life-Safety Assessment <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
