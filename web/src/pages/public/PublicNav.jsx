import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { rememberCta } from "@/lib/acquisition";

const NAV_LINKS = [
  { label: "The Problem", href: "/#problem" },
  { label: "Solution", href: "/#solution" },
  { label: "Who It's For", href: "/#industries" },
  { label: "Platform", href: "/true911-platform" },
  { label: "Request a Quote", href: "/quote" },
];

const LINK = "text-sm text-slate-300 hover:text-white transition-colors min-h-[44px] inline-flex items-center";

export default function PublicNav() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  const handleNavClick = (href) => {
    setOpen(false);
    const id = href.slice(2);
    if (location.pathname === "/") document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    else window.location.href = href;
  };

  const item = (link, mobile) => {
    const cls = mobile
      ? "flex w-full min-h-[44px] items-center px-3 text-sm text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg"
      : LINK;
    return link.href.startsWith("/#") ? (
      <button key={link.label} type="button" onClick={() => handleNavClick(link.href)} className={cls}>{link.label}</button>
    ) : (
      <Link key={link.label} to={link.href} onClick={() => setOpen(false)} className={cls}>{link.label}</Link>
    );
  };

  return (
    <nav aria-label="Main" className="fixed top-0 left-0 right-0 z-50 bg-slate-900/95 backdrop-blur-sm border-b border-slate-800">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:bg-white focus:text-slate-900 focus:px-3 focus:py-2 focus:rounded">
        Skip to content
      </a>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-2.5 min-h-[44px]" aria-label="True911 home">
            <img src="/brand/true911-beacon-reversed.svg" alt="" aria-hidden="true" className="w-9 h-9" />
            <span className="text-xl font-bold text-white tracking-tight">True911</span>
          </Link>

          <div className="hidden lg:flex items-center gap-6">
            {NAV_LINKS.map((l) => item(l, false))}
            <Link to="/login" className={`${LINK} ml-2`}>Log in</Link>
            <Link to="/get-started" onClick={() => rememberCta("nav_assessment")}
              className="min-h-[44px] inline-flex items-center px-4 bg-[#1C6FE6] hover:bg-[#12408F] text-white text-sm font-semibold rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF]">
              Start an Assessment
            </Link>
          </div>

          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="public-mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            className="lg:hidden w-11 h-11 inline-flex items-center justify-center text-slate-300 hover:text-white">
            {open ? <X className="w-6 h-6" aria-hidden="true" /> : <Menu className="w-6 h-6" aria-hidden="true" />}
          </button>
        </div>
      </div>

      {open && (
        <div id="public-mobile-menu" className="lg:hidden bg-slate-900 border-t border-slate-800 px-4 pb-4 pt-2 space-y-1">
          {NAV_LINKS.map((l) => item(l, true))}
          <Link to="/login" onClick={() => setOpen(false)}
            className="flex min-h-[44px] items-center px-3 text-sm text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg">
            Log in
          </Link>
          <Link to="/get-started" onClick={() => { setOpen(false); rememberCta("nav_assessment"); }}
            className="flex min-h-[44px] items-center justify-center mt-2 px-3 bg-[#1C6FE6] text-white text-sm font-semibold rounded-lg">
            Start a Life-Safety Assessment
          </Link>
        </div>
      )}
    </nav>
  );
}
