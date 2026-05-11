/**
 * Read-only view of a submitted (or in-progress) registration.
 *
 * Lives at /register/:registrationId.  The resume token is read from
 * the ?token=... query string; if missing, we fall back to the value
 * persisted in sessionStorage right after submission.
 *
 * Maps the backend's error contract to user-friendly screens:
 *   403 -> "wrong link"
 *   410 -> "link expired"
 *   404 -> "not found"
 */

import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Shield, AlertTriangle, Loader2, CheckCircle2, Clock, MapPin, Phone,
  Building2, User, Mail, ArrowLeft,
} from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";
import { RegistrationAPI } from "@/api/registrations";

const STATUS_LABELS = {
  draft: { label: "Draft — not yet submitted", color: "amber", icon: Clock },
  submitted: { label: "Submitted — awaiting review", color: "blue", icon: CheckCircle2 },
  internal_review: { label: "In review by our team", color: "blue", icon: CheckCircle2 },
  pending_customer_info: { label: "Waiting on additional info from you", color: "amber", icon: Clock },
  pending_equipment_assignment: { label: "Equipment being prepared", color: "blue", icon: Clock },
  pending_sim_assignment: { label: "Equipment being prepared", color: "blue", icon: Clock },
  pending_installer_schedule: { label: "Scheduling the installer", color: "blue", icon: Clock },
  scheduled: { label: "Installation scheduled", color: "emerald", icon: CheckCircle2 },
  installed: { label: "Installation complete — QA in progress", color: "emerald", icon: CheckCircle2 },
  qa_review: { label: "Final quality review", color: "blue", icon: Clock },
  ready_for_activation: { label: "Ready to activate", color: "emerald", icon: CheckCircle2 },
  active: { label: "Service active", color: "emerald", icon: CheckCircle2 },
  cancelled: { label: "Cancelled", color: "red", icon: AlertTriangle },
};

const COLOR_CLASSES = {
  amber: "bg-amber-500/15 border-amber-500/30 text-amber-300",
  blue: "bg-blue-500/15 border-blue-500/30 text-blue-300",
  emerald: "bg-emerald-500/15 border-emerald-500/30 text-emerald-300",
  red: "bg-red-500/15 border-red-500/30 text-red-300",
};


function FullPageMessage({ icon: Icon, color = "red", title, children }) {
  const colorClass = {
    red: "bg-red-500/15 ring-red-500/10 text-red-400",
    amber: "bg-amber-500/15 ring-amber-500/10 text-amber-400",
    slate: "bg-slate-500/15 ring-slate-500/10 text-slate-400",
  }[color];
  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />
      <main className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md mx-auto">
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
            <div className={`inline-flex items-center justify-center w-14 h-14 rounded-full ring-4 mb-4 ${colorClass}`}>
              <Icon className="w-7 h-7" />
            </div>
            <h1 className="text-xl font-bold text-white mb-2">{title}</h1>
            <div className="text-sm text-slate-400 mb-6">{children}</div>
            <Link
              to="/register"
              className="inline-flex items-center gap-1.5 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-xl"
            >
              Start a New Registration
            </Link>
            <Link
              to="/"
              className="block mt-3 text-xs text-slate-500 hover:text-slate-300"
            >
              <ArrowLeft className="w-3 h-3 inline mr-1" /> Back to Home
            </Link>
          </div>
        </div>
      </main>
      <PublicFooter />
    </div>
  );
}


export default function RegistrationView() {
  const { registrationId } = useParams();
  const [searchParams] = useSearchParams();
  const queryToken = searchParams.get("token");

  const [token, setToken] = useState(queryToken || "");
  const [registration, setRegistration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState(null);

  // Fallback to sessionStorage if no token in URL.  This covers the
  // "right after submit" case where Register.jsx persisted the token
  // before navigating.
  useEffect(() => {
    if (token) return;
    try {
      const raw = sessionStorage.getItem("t911_registration_last");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.registration_id === registrationId && parsed?.resume_token) {
          setToken(parsed.resume_token);
        }
      }
    } catch { /* ignore */ }
  }, [token, registrationId]);

  useEffect(() => {
    if (!token) {
      // Wait for the sessionStorage effect above to populate the token
      // before deciding it's missing.  We give it one tick.
      const t = setTimeout(() => {
        if (!token) {
          setErrorStatus(403);
          setLoading(false);
        }
      }, 50);
      return () => clearTimeout(t);
    }

    let cancelled = false;
    setLoading(true);
    setErrorStatus(null);
    RegistrationAPI.get(registrationId, token)
      .then((data) => {
        if (cancelled) return;
        setRegistration(data);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorStatus(err?.status || 500);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [registrationId, token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex flex-col">
        <PublicNav />
        <main className="flex-1 pt-28 pb-20 px-4 flex items-center justify-center">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading your registration…
          </div>
        </main>
        <PublicFooter />
      </div>
    );
  }

  if (errorStatus === 403) {
    return (
      <FullPageMessage icon={AlertTriangle} color="amber" title="That link doesn't look right">
        We couldn't verify the reference link. Double-check the URL you
        followed, or start a fresh registration.
      </FullPageMessage>
    );
  }
  if (errorStatus === 410) {
    return (
      <FullPageMessage icon={Clock} color="amber" title="This link has expired">
        Your reference link is no longer valid (links expire 30 days
        after you start a registration). Please start a new one.
      </FullPageMessage>
    );
  }
  if (errorStatus === 404) {
    return (
      <FullPageMessage icon={AlertTriangle} color="slate" title="Registration not found">
        We couldn't find a registration with that reference number.
      </FullPageMessage>
    );
  }
  if (errorStatus) {
    return (
      <FullPageMessage icon={AlertTriangle} color="red" title="Something went wrong">
        We hit an unexpected error loading your registration. Please try
        again in a moment, or email{" "}
        <a href="mailto:hello@true911.com" className="text-red-300 underline">hello@true911.com</a>.
      </FullPageMessage>
    );
  }

  if (!registration) return null;

  const statusInfo = STATUS_LABELS[registration.status] || { label: registration.status, color: "slate", icon: Clock };
  const StatusIcon = statusInfo.icon;
  const totalUnits = (registration.locations || []).reduce(
    (acc, l) => acc + (l.service_units?.length || 0),
    0,
  );

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />

      <main className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="flex items-start gap-3 mb-6">
            <div className="w-12 h-12 bg-red-600 rounded-xl flex items-center justify-center flex-shrink-0">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold text-white">{registration.customer_name || "Your Registration"}</h1>
              <p className="text-xs text-slate-400 font-mono">{registration.registration_id}</p>
            </div>
          </div>

          {/* Status badge */}
          <div className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm mb-6 ${COLOR_CLASSES[statusInfo.color] || COLOR_CLASSES.blue}`}>
            <StatusIcon className="w-4 h-4 flex-shrink-0" />
            <span className="font-medium">{statusInfo.label}</span>
          </div>

          {/* Quick stats */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-white">{registration.locations?.length || 0}</div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500">Locations</div>
            </div>
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-white">{totalUnits}</div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500">Emergency Phones</div>
            </div>
          </div>

          {/* Detail cards */}
          <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 mb-4">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <Building2 className="w-4 h-4 text-red-400" /> Company
            </h3>
            <dl className="space-y-1.5 text-sm">
              <DetailRow label="Company" value={registration.customer_name} />
              <DetailRow label="Submitted by" value={registration.submitter_name} />
              <DetailRow label="Email" value={registration.submitter_email} />
              <DetailRow label="Phone" value={registration.submitter_phone} />
            </dl>
          </div>

          <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 mb-4">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <User className="w-4 h-4 text-red-400" /> Main Contact
            </h3>
            <dl className="space-y-1.5 text-sm">
              <DetailRow label="Name" value={registration.poc_name} />
              <DetailRow label="Phone" value={registration.poc_phone} />
              <DetailRow label="Email" value={registration.poc_email} />
              <DetailRow label="Role" value={registration.poc_role} />
            </dl>
          </div>

          {(registration.locations || []).map((loc) => (
            <div key={loc.id} className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 mb-4">
              <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-red-400" /> {loc.location_label}
              </h3>
              <p className="text-sm text-slate-400 mb-3">
                {[loc.street, loc.city, loc.state, loc.zip].filter(Boolean).join(", ") || <em className="text-slate-600">Address not provided</em>}
              </p>
              {loc.dispatchable_description && (
                <p className="text-xs text-slate-400 mb-3">
                  <strong className="text-slate-300">Dispatch detail:</strong> {loc.dispatchable_description}
                </p>
              )}
              {(loc.service_units || []).length > 0 && (
                <ul className="space-y-1">
                  {loc.service_units.map((u) => (
                    <li key={u.id} className="text-sm text-slate-300 flex items-center gap-2">
                      <Phone className="w-3 h-3 text-slate-500" />
                      {u.unit_label}
                      {u.phone_number_existing && <span className="text-slate-500">({u.phone_number_existing})</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}

          <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3 text-xs text-blue-200 flex items-start gap-2">
            <Mail className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-400" />
            <div>
              Need to change something? Email{" "}
              <a href="mailto:hello@true911.com" className="text-blue-300 underline">
                hello@true911.com
              </a>{" "}
              with your reference number{" "}
              <span className="font-mono text-white">{registration.registration_id}</span>.
            </div>
          </div>

          <div className="text-center mt-6">
            <Link to="/" className="text-xs text-slate-500 hover:text-slate-300">
              <ArrowLeft className="w-3 h-3 inline mr-1" /> Back to Home
            </Link>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-[10px] uppercase tracking-wide text-slate-500 pt-0.5">{label}</dt>
      <dd className="text-slate-200 text-right">
        {value || <span className="italic text-slate-600">not set</span>}
      </dd>
    </div>
  );
}
