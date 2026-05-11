/**
 * Post-submit confirmation page.
 *
 * Reaches this route only after Register.jsx has successfully POSTed
 * and submitted a registration.  We persist the just-issued
 * registration_id + resume_token in sessionStorage so a refresh on
 * this page still shows the customer their reference number and a
 * "view my submission" link.
 */

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, Mail, Copy, ArrowRight, Shield } from "lucide-react";
import PublicNav from "./PublicNav";
import PublicFooter from "./PublicFooter";

export default function RegistrationThanks() {
  const { registrationId } = useParams();
  const [last, setLast] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("t911_registration_last");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.registration_id === registrationId) {
          setLast(parsed);
        }
      }
    } catch { /* ignore */ }
  }, [registrationId]);

  const referenceUrl = last
    ? `${window.location.origin}/register/${last.registration_id}?token=${encodeURIComponent(last.resume_token)}`
    : null;

  const copyReference = async () => {
    if (!referenceUrl) return;
    try {
      await navigator.clipboard.writeText(referenceUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch { /* clipboard blocked — silent */ }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col">
      <PublicNav />

      <main className="flex-1 pt-28 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-xl mx-auto">
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center shadow-xl">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-500/15 ring-4 ring-emerald-500/10 rounded-full mb-5">
              <CheckCircle2 className="w-8 h-8 text-emerald-400" />
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">You're all set!</h1>
            <p className="text-sm text-slate-400 mb-6">
              Your registration has been received. Our team will follow up
              within one business day to confirm everything and schedule
              your installation.
            </p>

            <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-3 mb-5">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Reference Number</div>
              <div className="text-base font-mono font-semibold text-white">{registrationId}</div>
            </div>

            {referenceUrl && (
              <div className="text-left mb-6">
                <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                  Bookmark or save this link to view your submission later
                </div>
                <div className="flex items-stretch gap-2">
                  <input
                    readOnly
                    value={referenceUrl}
                    onFocus={(e) => e.target.select()}
                    className="flex-1 px-3 py-2 bg-slate-900/80 border border-slate-700 rounded-lg text-[11px] font-mono text-slate-300 truncate"
                  />
                  <button
                    onClick={copyReference}
                    className="inline-flex items-center gap-1 px-3 py-2 bg-slate-700/60 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <p className="text-[11px] text-slate-500 mt-2">
                  This link is private. Anyone with it can view your registration details, so don't share it publicly. The link expires in 30 days.
                </p>
              </div>
            )}

            <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3 mb-6 text-left text-xs text-blue-200 flex items-start gap-2">
              <Mail className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-400" />
              <div>
                <strong className="text-white">What's next?</strong> Watch your
                inbox for a confirmation email and follow-up call. If you don't
                hear from us within one business day, reach out to{" "}
                <a href="mailto:hello@true911.com" className="text-blue-300 underline">
                  hello@true911.com
                </a>.
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2 justify-center">
              {referenceUrl && (
                <Link
                  to={`/register/${registrationId}?token=${encodeURIComponent(last.resume_token)}`}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-xl"
                >
                  View My Submission <ArrowRight className="w-4 h-4" />
                </Link>
              )}
              <Link
                to="/"
                className="inline-flex items-center gap-1.5 px-4 py-2.5 border border-slate-700 hover:border-slate-600 text-slate-200 text-sm font-medium rounded-xl"
              >
                Back to Home
              </Link>
            </div>
          </div>

          <p className="text-center text-[11px] text-slate-600 mt-6 flex items-center justify-center gap-1.5">
            <Shield className="w-3 h-3" />
            Made in USA · NDAA-TAA Compliant
          </p>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
