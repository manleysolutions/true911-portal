import { useState, useEffect } from "react";
import { createPageUrl } from "@/utils";
import { Shield, Eye, EyeOff, Lock, AlertTriangle, UserPlus } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { isDemo } from "@/config";

const DEMO_ROLES = [
  {
    role: "Admin",
    email: "admin@true911.com",
    password: "admin123",
    desc: "Full access — all actions, admin tools, E911 changes",
    capabilities: ["Ping", "Reboot", "E911 Update", "Admin Panel", "Reports"],
    color: "border-red-200 bg-red-50 hover:border-red-300",
    badgeColor: "bg-red-100 text-red-700",
  },
  {
    role: "Manager",
    email: "manager@true911.com",
    password: "manager123",
    desc: "Operational access — ping, ack incidents, generate reports",
    capabilities: ["Ping", "Ack Incidents", "Reports", "View Admin"],
    color: "border-blue-200 bg-blue-50 hover:border-blue-300",
    badgeColor: "bg-blue-100 text-blue-700",
  },
  {
    role: "User",
    email: "user@true911.com",
    password: "user123",
    desc: "Read-only access — view sites, status, reports",
    capabilities: ["View Sites", "View Incidents", "View Reports"],
    color: "border-gray-200 bg-gray-50 hover:border-gray-300",
    badgeColor: "bg-gray-100 text-gray-600",
  },
];

export default function AuthGate() {
  const { user, login, register, ready } = useAuth();
  const [tab, setTab] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [quickLoading, setQuickLoading] = useState(null);

  useEffect(() => {
    if (ready && user) {
      window.location.href = createPageUrl("Overview");
    }
  }, [user, ready]);

  const resetForm = () => {
    setError("");
    setEmail("");
    setPassword("");
    setName("");
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      window.location.href = createPageUrl("Overview");
    } catch (err) {
      setError(err?.message || "Invalid credentials. Please check your email and password.");
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(email, password, name);
      window.location.href = createPageUrl("Overview");
    } catch (err) {
      setError(err?.message || "Registration failed. Please try again.");
      setLoading(false);
    }
  };

  const quickLogin = async (acc) => {
    setError("");
    setEmail(acc.email);
    setPassword(acc.password);
    setQuickLoading(acc.role);
    try {
      await login(acc.email, acc.password);
      window.location.href = createPageUrl("Overview");
    } catch {
      setError("Login failed. Check backend connection.");
      setQuickLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col justify-center items-center px-4">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-red-600 rounded-2xl shadow-2xl mb-4 ring-4 ring-red-500/20">
            <Shield className="w-8 h-8 text-white" />
          </div>
          <div className="text-3xl font-bold text-white tracking-tight">
            True911<span className="text-red-500">+</span>
          </div>
          <div className="text-xs text-slate-400 mt-1 font-medium tracking-widest uppercase">{isDemo ? "NOC Demo Portal" : "NOC Portal"}</div>
          <p className="text-sm text-slate-400 mt-2">Life-Safety Device Monitoring & Management</p>
        </div>

        {/* Demo environment banner */}
        {isDemo && (
          <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3 mb-6">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <p className="text-xs text-amber-300 font-medium">
              Demo Environment — All actions are simulated. No live devices are connected.
            </p>
          </div>
        )}

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl p-7">
          {/* Tab switcher (prod only - demo doesn't need register) */}
          {!isDemo && (
            <div className="flex mb-5 border-b border-gray-100">
              <button
                onClick={() => { setTab("login"); resetForm(); }}
                className={`flex items-center gap-1.5 pb-2.5 px-3 text-sm font-semibold border-b-2 transition-colors ${
                  tab === "login"
                    ? "border-red-600 text-gray-900"
                    : "border-transparent text-gray-400 hover:text-gray-600"
                }`}
              >
                <Lock className="w-3.5 h-3.5" /> Sign In
              </button>
              <button
                onClick={() => { setTab("register"); resetForm(); }}
                className={`flex items-center gap-1.5 pb-2.5 px-3 text-sm font-semibold border-b-2 transition-colors ${
                  tab === "register"
                    ? "border-red-600 text-gray-900"
                    : "border-transparent text-gray-400 hover:text-gray-600"
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" /> Register
              </button>
            </div>
          )}

          {/* Demo mode: always show sign-in header */}
          {isDemo && (
            <div className="flex items-center gap-2 mb-5">
              <Lock className="w-4 h-4 text-gray-400" />
              <h2 className="text-base font-semibold text-gray-900">Sign In to Continue</h2>
            </div>
          )}

          {/* Login form */}
          {(tab === "login" || isDemo) && (
            <form onSubmit={handleLogin} className="space-y-4 mb-6">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                  placeholder="you@true911.com"
                  required
                  autoComplete="email"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all pr-12"
                    placeholder="Enter password"
                    required
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {error && tab === "login" && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-3 px-4 rounded-xl transition-colors text-sm shadow-sm"
              >
                {loading ? "Signing in..." : "Sign In"}
              </button>
            </form>
          )}

          {/* Register form (prod only) */}
          {tab === "register" && !isDemo && (
            <form onSubmit={handleRegister} className="space-y-4 mb-6">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                  placeholder="Jane Smith"
                  required
                  autoComplete="name"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Email Address</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                  placeholder="you@true911.com"
                  required
                  autoComplete="email"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all pr-12"
                    placeholder="Min 12 chars, uppercase, lowercase, digit"
                    required
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 mt-1">At least 12 characters with uppercase, lowercase, and a digit.</p>
              </div>

              {error && tab === "register" && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-3 px-4 rounded-xl transition-colors text-sm shadow-sm"
              >
                {loading ? "Creating account..." : "Create Account"}
              </button>
            </form>
          )}

          {/* Demo role picker */}
          {isDemo && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <div className="flex-1 h-px bg-gray-100" />
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Demo Role</span>
                <div className="flex-1 h-px bg-gray-100" />
              </div>
              <p className="text-xs text-gray-500 mb-3 text-center">Select a role to preview permissions and auto-fill credentials</p>

              <div className="space-y-2">
                {DEMO_ROLES.map(acc => (
                  <button
                    key={acc.role}
                    onClick={() => quickLogin(acc)}
                    disabled={quickLoading !== null}
                    className={`w-full flex items-start justify-between px-4 py-3 border rounded-xl text-sm transition-all group ${acc.color} ${quickLoading !== null ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    <div className="flex items-start gap-3 text-left">
                      <span className={`mt-0.5 text-[10px] font-bold px-2 py-0.5 rounded-full ${acc.badgeColor} flex-shrink-0`}>
                        {acc.role}
                      </span>
                      <div>
                        <div className="text-xs font-medium text-gray-800 group-hover:text-gray-900">{acc.desc}</div>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {acc.capabilities.map(cap => (
                            <span key={cap} className="text-[10px] text-gray-500 bg-white/60 px-1.5 py-0.5 rounded border border-gray-200">
                              {cap}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    {quickLoading === acc.role ? (
                      <span className="ml-2 mt-1 w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    ) : (
                      <span className="text-[10px] text-gray-400 font-mono flex-shrink-0 mt-0.5 ml-2">{acc.password}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="text-center mt-6 flex items-center justify-center gap-3">
          <span className="text-blue-400 text-xs font-bold">Made in USA</span>
          <span className="text-slate-600">·</span>
          <span className="text-slate-500 text-xs font-medium">NDAA-TAA Compliant</span>
          <span className="text-slate-600">·</span>
          <span className="text-slate-500 text-xs">© 2026 Manley Solutions</span>
        </div>
      </div>
    </div>
  );
}
