// Shared, accessible pieces for the public acquisition forms (D-031).
// Real <label htmlFor>, aria-describedby for hints + errors, aria-invalid,
// aria-pressed toggles, >=44px targets.  Brand blue for action; red is reserved
// for risk/errors (D-033).
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle, ArrowLeft } from "lucide-react";
import { apiFetch } from "@/api/client";
import { getAttribution, newIdempotencyKey, submitAcquisition } from "@/lib/acquisition";

const post = (path, body) => apiFetch(path, { method: "POST", body: JSON.stringify(body) });

/** Submission state for one public form.  The idempotency key lives for the
 *  whole attempt (reused on retry), and the receipt is set ONLY from a server
 *  receipt — never on 404 / network / 5xx (D-031). */
export function useLeadSubmission(path) {
  const key = useRef(newIdempotencyKey());
  const [loading, setLoading] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState({});
  const submit = async (payload) => {
    setError(""); setErrors({}); setLoading(true);
    try {
      const r = await submitAcquisition(post, path, {
        ...payload, idempotency_key: key.current, attribution: getAttribution(),
      });
      setReceipt(r);
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  return { submit, loading, receipt, error, errors };
}

const INPUT =
  "w-full min-h-[44px] px-4 py-3 bg-slate-900/60 border rounded-xl text-sm text-white placeholder-slate-500 " +
  "focus:outline-none focus:ring-2 focus:ring-[#60A9FF] focus:border-transparent transition-all";

export function Field({ id, label, required, hint, error, as = "input", ...props }) {
  const Tag = as;
  const hintId = hint ? `${id}-hint` : null;
  const errId = error ? `${id}-error` : null;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-semibold text-slate-300 mb-1.5 uppercase tracking-wide">
        {label}{required && <span aria-hidden="true"> *</span>}
        {required && <span className="sr-only"> (required)</span>}
      </label>
      <Tag id={id} name={id} required={required} aria-required={required || undefined}
        aria-invalid={error ? true : undefined} aria-describedby={describedBy}
        className={`${INPUT} ${error ? "border-red-400" : "border-slate-600"} ${as === "textarea" ? "resize-y" : ""}`}
        {...props} />
      {hint && <p id={hintId} className="mt-1 text-xs text-slate-400">{hint}</p>}
      {error && <p id={errId} className="mt-1 text-xs text-red-300">{error}</p>}
    </div>
  );
}

export function ToggleGroup({ label, hint, options, selected, onToggle, idPrefix }) {
  const hintId = hint ? `${idPrefix}-hint` : undefined;
  return (
    <fieldset aria-describedby={hintId}>
      <legend className="block text-xs font-semibold text-slate-300 mb-2 uppercase tracking-wide">{label}</legend>
      {hint && <p id={hintId} className="-mt-1 mb-2 text-xs text-slate-400">{hint}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {options.map((o) => {
          const on = selected.includes(o.value);
          return (
            <button key={o.value} type="button" aria-pressed={on} onClick={() => onToggle(o.value)}
              className={`min-h-[44px] flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm text-left border transition-all
                focus:outline-none focus-visible:ring-2 focus-visible:ring-[#60A9FF] ${
                on ? "bg-[#2D8CFF]/15 border-[#60A9FF]/60 text-white" : "bg-slate-900/40 border-slate-600 text-slate-300 hover:border-slate-400"}`}>
              <span aria-hidden="true" className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center ${
                on ? "bg-[#1C6FE6] border-[#60A9FF]" : "border-slate-500"}`}>
                {on && <CheckCircle className="w-3 h-3 text-white" />}
              </span>
              {o.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function SubmitError({ message }) {
  const ref = useRef(null);
  useEffect(() => { if (message) ref.current?.focus(); }, [message]);
  if (!message) return null;
  return (
    <div ref={ref} tabIndex={-1} role="alert"
      className="flex items-start gap-2 bg-red-500/10 border border-red-400/40 text-red-200 text-sm px-4 py-3 rounded-xl focus:outline-none focus:ring-2 focus:ring-red-300">
      <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <span>{message} Your answers are still here.</span>
    </div>
  );
}

export function SubmitButton({ loading, children }) {
  return (
    <button type="submit" disabled={loading} aria-busy={loading || undefined}
      className="w-full min-h-[48px] bg-[#1C6FE6] hover:bg-[#12408F] disabled:opacity-60 text-white font-semibold py-3.5 px-4 rounded-xl transition-colors text-sm
        focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 focus-visible:ring-[#60A9FF]">
      {loading ? "Sending…" : children}
    </button>
  );
}

/** Honeypot: visually hidden, skipped by keyboard and assistive tech. */
export function Honeypot({ value, onChange }) {
  return (
    <div aria-hidden="true" style={{ position: "absolute", left: "-10000px", width: 1, height: 1, overflow: "hidden" }}>
      <label htmlFor="website">Website</label>
      <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" value={value} onChange={onChange} />
    </div>
  );
}

/** Shown ONLY with a server receipt (record_ref proves durability). */
export function Received({ title, receipt, children }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return (
    <div ref={ref} tabIndex={-1} role="status"
      className="bg-slate-800/60 border border-slate-600/60 rounded-2xl p-8 text-center focus:outline-none">
      <div className="inline-flex items-center justify-center w-12 h-12 bg-emerald-500/10 rounded-full mb-4">
        <CheckCircle className="w-6 h-6 text-emerald-400" aria-hidden="true" />
      </div>
      <h2 className="text-xl font-semibold mb-2">{title}</h2>
      <p className="text-sm text-slate-300 mb-2">{children}</p>
      <p className="text-xs text-slate-400 mb-6">Reference <span className="font-mono text-slate-200">{receipt.record_ref}</span></p>
      <Link to="/" className="inline-flex items-center gap-1.5 min-h-[44px] text-sm text-[#60A9FF] hover:text-white font-medium">
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" /> Back to home
      </Link>
    </div>
  );
}

/** Map FastAPI 422 detail entries to per-field messages. */
export function fieldErrors(err) {
  const detail = err?.cause?.body?.detail;
  const out = {};
  if (Array.isArray(detail)) {
    for (const d of detail) {
      const f = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null;
      if (typeof f === "string" && !out[f]) out[f] = f === "email" ? "Enter a valid email address." : "Please check this field.";
    }
  }
  return out;
}
