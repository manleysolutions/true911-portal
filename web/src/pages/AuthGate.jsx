import { useState, useEffect } from "react";
import { createPageUrl } from "@/utils";
import { Shield, Eye, EyeOff, Lock, AlertTriangle, UserPlus, Mail, CheckCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { isDemo } from "@/config";
import { apiFetch, setTokens } from "@/api/client";

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
  const [tab, setTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [quickLoading, setQuickLoading] = useState(null);

  // Invite flow state
  const [inviteToken, setInviteToken] = useState(null);
  const [inviteInfo, setInviteInfo] = useState(null); // { email, name, role }
  const [inviteError, setInviteError] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [invitePassword, setInvitePassword] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [showInvitePassword, setShowInvitePassword] = useState(false);
  const [inviteAccepted, setInviteAccepted] = useState(false);

  // Must-change-password flow
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);

  // Check for invite token in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("invite");
    if (token) {
      setInviteToken(token);
      setInviteLoading(true);
      apiFetch(`/auth/invite/${token}`)
        .then((info) => {
          setInviteInfo(info);
          setInviteName(info.name);
        })
        .catch((err) => {
          setInviteError(err?.message || "Invalid or expired invite link");
        })
        .finally(() => setInviteLoading(false));
    }
  }, []);

  useEffect(() => {
    if (ready && user && !mustChangePassword) {
      window.location.href = createPageUrl("Overview");
    }
  }, [user, ready, mustChangePassword]);

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
      const data = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });

      if (data.must_change_password) {
        setTokens(data.access_token, data.refresh_token);
        setCurrentPassword(password);
        setMustChangePassword(true);
        setLoading(false);
        return;
      }

      await login(email, password);
      window.location.href = createPageUrl("Overview");
    } catch (err) {
      setError(err?.message || "Invalid credentials. Please check your email and password.");
      setLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setMustChangePassword(false);
      window.location.href = createPageUrl("Overview");
    } catch (err) {
      setError(err?.message || "Failed to change password");
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

  const handleInviteAccept = async (e) => {
    e.preventDefault();
    setInviteError("");
    setInviteLoading(true);
    try {
      const data = await apiFetch(`/auth/invite/${inviteToken}/accept`, {
        method: "POST",
        body: JSON.stringify({ password: invitePassword, name: inviteName || undefined }),
      });
      setTokens(data.access_token, data.refresh_token);
      setInviteAccepted(true);
      setTimeout(() => {
        window.location.href = createPageUrl("Overview");
      }, 1500);
    } catch (err) {
      setInviteError(err?.message || "Failed to set up your account");
      setInviteLoading(false);
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

  // ── Invite acceptance view ──
  if (inviteToken) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col justify-center items-center px-4">
        <div className="w-full max-w-lg">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-red-600 rounded-2xl shadow-2xl mb-4 ring-4 ring-red-500/20">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <div className="text-3xl font-bold text-white tracking-tight">
              True911<span className="text-red-500">+</span>
            </div>
            <div className="text-xs text-slate-400 mt-1 font-medium tracking-widest uppercase">NOC Portal</div>
          </div>

          <div className="bg-white rounded-2xl shadow-2xl p-7">
            {inviteLoading && !inviteInfo && !inviteError && (
              <div className="flex flex-col items-center py-8">
                <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin mb-4" />
                <p className="text-sm text-gray-500">Validating invite link...</p>
              </div>
            )}

            {inviteError && !inviteInfo && (
              <div className="text-center py-6">
                <div className="inline-flex items-center justify-center w-12 h-12 bg-red-50 rounded-full mb-4">
                  <AlertTriangle className="w-6 h-6 text-red-500" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900 mb-2">Invalid Invite Link</h2>
                <p className="text-sm text-gray-500 mb-4">{inviteError}</p>
                <p className="text-xs text-gray-400">Contact your administrator for a new invite link.</p>
                <a href="/AuthGate" className="inline-block mt-4 text-sm text-red-600 hover:text-red-700 font-medium">Back to Sign In</a>
              </div>
            )}

            {inviteAccepted && (
              <div className="text-center py-6">
                <div className="inline-flex items-center justify-center w-12 h-12 bg-emerald-50 rounded-full mb-4">
                  <CheckCircle className="w-6 h-6 text-emerald-500" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900 mb-2">Account Created!</h2>
                <p className="text-sm text-gray-500">Redirecting you to the portal...</p>
              </div>
            )}

            {inviteInfo && !inviteAccepted && (
              <>
                <div className="flex items-center gap-2 mb-1">
                  <Mail className="w-4 h-4 text-red-500" />
                  <h2 className="text-base font-semibold text-gray-900">You're Invited!</h2>
                </div>
                <p className="text-sm text-gray-500 mb-5">
                  Welcome, <strong>{inviteInfo.name}</strong>! Set your password to get started.
                </p>

                <div className="bg-gray-50 rounded-lg px-4 py-3 mb-5 space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Email</span>
                    <span className="font-medium text-gray-700">{inviteInfo.email}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Role</span>
                    <span className="font-medium text-gray-700">{inviteInfo.role}</span>
                  </div>
                </div>

                <form onSubmit={handleInviteAccept} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Your Name</label>
                    <input
                      type="text"
                      value={inviteName}
                      onChange={e => setInviteName(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                      placeholder={inviteInfo.name}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Set Password</label>
                    <div className="relative">
                      <input
                        type={showInvitePassword ? "text" : "password"}
                        value={invitePassword}
                        onChange={e => setInvitePassword(e.target.value)}
                        className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all pr-12"
                        placeholder="Min 12 chars, uppercase, lowercase, digit"
                        required
                        autoComplete="new-password"
                      />
                      <button
                        type="button"
                        onClick={() => setShowInvitePassword(!showInvitePassword)}
                        className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      >
                        {showInvitePassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    <p className="text-[10px] text-gray-400 mt-1">At least 12 characters with uppercase, lowercase, and a digit.</p>
                  </div>

                  {inviteError && (
                    <div className="flex items-start gap-2 bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                      {inviteError}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={inviteLoading}
                    className="w-full bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-3 px-4 rounded-xl transition-colors text-sm shadow-sm"
                  >
                    {inviteLoading ? "Setting up account..." : "Create My Account"}
                  </button>
                </form>
              </>
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

  // ── Must-change-password view ──
  if (mustChangePassword) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col justify-center items-center px-4">
        <div className="w-full max-w-lg">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-red-600 rounded-2xl shadow-2xl mb-4 ring-4 ring-red-500/20">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <div className="text-3xl font-bold text-white tracking-tight">
              True911<span className="text-red-500">+</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-2xl p-7">
            <div className="flex items-center gap-2 mb-1">
              <Lock className="w-4 h-4 text-amber-500" />
              <h2 className="text-base font-semibold text-gray-900">Change Your Password</h2>
            </div>
            <p className="text-sm text-gray-500 mb-5">Your administrator requires you to set a new password before continuing.</p>

            <form onSubmit={handleChangePassword} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">New Password</label>
                <div className="relative">
                  <input
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all pr-12"
                    placeholder="Min 12 chars, uppercase, lowercase, digit"
                    required
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 mt-1">At least 12 characters with uppercase, lowercase, and a digit.</p>
              </div>

              {error && (
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
                {loading ? "Updating password..." : "Set New Password & Continue"}
              </button>
            </form>
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

  // ── Main login/register view ──
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
          {/* Tab switcher (demo mode — show only login) */}
          {/* In production: only show Sign In (no Register tab — admins create users) */}
          {/* In demo: always show Sign In header */}
          {isDemo ? (
            <div className="flex items-center gap-2 mb-5">
              <Lock className="w-4 h-4 text-gray-400" />
              <h2 className="text-base font-semibold text-gray-900">Sign In to Continue</h2>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-5">
              <Lock className="w-4 h-4 text-gray-400" />
              <h2 className="text-base font-semibold text-gray-900">Sign In</h2>
            </div>
          )}

          {/* Login form */}
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

            {error && (
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
