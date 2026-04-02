import { Link } from "react-router-dom";
import { Shield } from "lucide-react";

export default function PublicFooter() {
  return (
    <footer className="bg-slate-950 border-t border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="md:col-span-1">
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-9 h-9 bg-red-600 rounded-lg flex items-center justify-center">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <span className="text-xl font-bold text-white tracking-tight">
                True911<span className="text-red-500">+</span>
              </span>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed">
              Life-safety device monitoring, management, and compliance for mission-critical environments.
            </p>
          </div>

          {/* Solutions */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider">Solutions</h4>
            <ul className="space-y-2">
              <li><a href="/#services" className="text-sm text-slate-400 hover:text-white transition-colors">Device Monitoring</a></li>
              <li><a href="/#services" className="text-sm text-slate-400 hover:text-white transition-colors">E911 Compliance</a></li>
              <li><a href="/#services" className="text-sm text-slate-400 hover:text-white transition-colors">NOC Operations</a></li>
              <li><a href="/#services" className="text-sm text-slate-400 hover:text-white transition-colors">Incident Management</a></li>
            </ul>
          </div>

          {/* Company */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider">Company</h4>
            <ul className="space-y-2">
              <li><Link to="/get-started" className="text-sm text-slate-400 hover:text-white transition-colors">Get Started</Link></li>
              <li><Link to="/quote" className="text-sm text-slate-400 hover:text-white transition-colors">Build a Quote</Link></li>
              <li><Link to="/login" className="text-sm text-slate-400 hover:text-white transition-colors">Portal Login</Link></li>
            </ul>
          </div>

          {/* Compliance */}
          <div>
            <h4 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider">Compliance</h4>
            <ul className="space-y-2">
              <li className="text-sm text-slate-400">NDAA-TAA Compliant</li>
              <li className="text-sm text-slate-400">Kari's Law / RAY BAUM's Act</li>
              <li className="text-sm text-slate-400">FCC E911 Regulations</li>
              <li className="text-sm text-blue-400 font-medium">Made in USA</li>
            </ul>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-slate-500">&copy; {new Date().getFullYear()} Manley Solutions LLC. All rights reserved.</p>
          <div className="flex items-center gap-4">
            <span className="text-blue-400 text-xs font-bold">Made in USA</span>
            <span className="text-slate-700">&middot;</span>
            <span className="text-slate-500 text-xs">NDAA-TAA Compliant</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
