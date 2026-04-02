import { useState, useEffect } from "react";
import { CheckCircle, AlertCircle, XCircle, RefreshCw, MessageSquare, Phone, Loader2 } from "lucide-react";

const STEPS = [
  { label: "Checking device", delay: 600 },
  { label: "Checking connection", delay: 800 },
  { label: "Checking voice service", delay: 700 },
];

const RESULT_MAP = {
  operational: {
    icon: CheckCircle,
    title: "Your system looks good",
    desc: "Your device appears to be operating normally.",
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
  },
  attention: {
    icon: AlertCircle,
    title: "Your system may need attention",
    desc: "We found something that may need a look. This doesn't necessarily mean there's a problem.",
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
  },
  impacted: {
    icon: XCircle,
    title: "We could not confirm normal service",
    desc: "We weren't able to verify everything is working as expected. We recommend contacting support.",
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
  },
};

export default function CustomerSystemTestResult({
  visible,
  running,
  result,
  onRunAgain,
  onChatAbout,
  onRequestHelp,
}) {
  const [currentStep, setCurrentStep] = useState(0);
  const [showResult, setShowResult] = useState(false);

  // Animate steps while running
  useEffect(() => {
    if (!running) {
      if (result) setShowResult(true);
      return;
    }
    setShowResult(false);
    setCurrentStep(0);

    let step = 0;
    const timers = [];
    let cumulative = 0;

    STEPS.forEach((s, i) => {
      cumulative += s.delay;
      timers.push(setTimeout(() => setCurrentStep(i + 1), cumulative));
    });

    return () => timers.forEach(clearTimeout);
  }, [running, result]);

  if (!visible) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-800 mb-3">System Test</h3>

      {/* Running state */}
      {running && (
        <div className="space-y-2">
          {STEPS.map((step, i) => (
            <div key={i} className="flex items-center gap-2">
              {i < currentStep ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : i === currentStep ? (
                <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
              ) : (
                <div className="w-4 h-4 rounded-full border border-gray-200" />
              )}
              <span className={`text-xs ${i <= currentStep ? "text-gray-700" : "text-gray-400"}`}>
                {step.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Result state */}
      {showResult && !running && result && (
        <>
          <ResultDisplay status={result} />
          <div className="flex flex-wrap gap-2 mt-3">
            <SmallButton icon={RefreshCw} label="Run Again" onClick={onRunAgain} />
            <SmallButton icon={MessageSquare} label="Chat About Results" onClick={onChatAbout} />
            {result !== "operational" && (
              <SmallButton icon={Phone} label="Request Help" onClick={onRequestHelp} variant="dark" />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ResultDisplay({ status }) {
  const r = RESULT_MAP[status] || RESULT_MAP.operational;
  const Icon = r.icon;

  return (
    <div className={`${r.bg} border ${r.border} rounded-lg p-3 flex items-start gap-3`}>
      <Icon className={`w-5 h-5 ${r.color} flex-shrink-0 mt-0.5`} />
      <div>
        <p className={`text-sm font-medium ${r.color}`}>{r.title}</p>
        <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{r.desc}</p>
      </div>
    </div>
  );
}

function SmallButton({ icon: Icon, label, onClick, variant = "default" }) {
  const styles = variant === "dark"
    ? "bg-gray-800 hover:bg-gray-900 text-white"
    : "bg-white hover:bg-gray-50 text-gray-700 border border-gray-200";

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1 text-[11px] font-medium px-2.5 py-1.5 rounded-lg transition-colors ${styles}`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </button>
  );
}
