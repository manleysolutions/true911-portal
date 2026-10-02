import { Link } from "react-router-dom";

// No blanket origin or procurement claims (D-030): "Made in USA" and
// "NDAA-TAA Compliant" were removed — such claims belong only on a specific,
// evidenced offering.
export default function PublicFooter() {
  return (
    <footer className="bg-slate-950 border-t border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div>
            <div className="flex items-center gap-2.5 mb-4">
              <img src="/brand/true911-beacon-reversed.svg" alt="" aria-hidden="true" className="w-9 h-9" />
              <span className="text-xl font-bold text-white tracking-tight">True911</span>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed">
              The operating system for life-safety communications: elevator phones, fire alarm communications and
              emergency phones across every location.
            </p>
          </div>

          <nav aria-label="Get started">
            <h2 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider">Get started</h2>
            <ul className="space-y-1">
              <li><Link to="/get-started" className="inline-block py-1.5 text-sm text-slate-300 hover:text-white">Life-Safety Assessment</Link></li>
              <li><Link to="/quote" className="inline-block py-1.5 text-sm text-slate-300 hover:text-white">Request a quote</Link></li>
              <li><Link to="/true911-platform" className="inline-block py-1.5 text-sm text-slate-300 hover:text-white">Platform overview</Link></li>
            </ul>
          </nav>

          <nav aria-label="Customers">
            <h2 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider">Customers</h2>
            <ul className="space-y-1">
              <li><Link to="/login" className="inline-block py-1.5 text-sm text-slate-300 hover:text-white">Customer login</Link></li>
            </ul>
          </nav>
        </div>

        <div className="mt-10 pt-6 border-t border-slate-800">
          <p className="text-xs text-slate-400">&copy; {new Date().getFullYear()} Manley Solutions LLC. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
