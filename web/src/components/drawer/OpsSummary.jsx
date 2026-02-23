import { Zap, CheckCircle } from "lucide-react";

function getIssuesAndSteps(site) {
  const issues = [];
  const nextSteps = [];

  if (site.status === "Not Connected") {
    issues.push("Device is offline — no response received.");
    nextSteps.push("Ping device to check connectivity");
    nextSteps.push("Check carrier signal and SIM status");
    nextSteps.push("Initiate remote reboot if accessible");
    nextSteps.push("Dispatch field tech if no recovery within 1h");
  } else if (site.status === "Attention Needed") {
    issues.push("Device is experiencing degraded connectivity.");
    nextSteps.push("Ping device to confirm signal quality");
    nextSteps.push("Review modem telemetry for interference");
    nextSteps.push("Consider SIM swap or antenna boost");
  } else if (site.status === "Unknown") {
    issues.push("Device status indeterminate — contact lost.");
    nextSteps.push("Attempt ping and review last telemetry event");
    nextSteps.push("Contact site POC to confirm physical status");
    nextSteps.push("Mark site for account review if no response");
  } else {
    nextSteps.push("Continue monitoring per heartbeat schedule");
    nextSteps.push("Verify next heartbeat due date is current");
  }

  if (site.signal_dbm && site.signal_dbm < -85) {
    issues.push(`Weak signal at ${site.signal_dbm} dBm (threshold: −85 dBm).`);
  }

  const daysOld = site.last_checkin
    ? Math.floor((Date.now() - new Date(site.last_checkin)) / 86400000)
    : null;
  if (daysOld > 7) {
    issues.push(`Last check-in was ${daysOld}d ago — possible heartbeat violation.`);
  }

  return { issues, nextSteps };
}

export default function OpsSummary({ site }) {
  const { issues, nextSteps } = getIssuesAndSteps(site);
  const isOk = site.status === "Connected" && issues.length === 0;

  if (isOk) {
    return (
      <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2.5">
        <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
        <div>
          <div className="text-xs font-semibold text-emerald-800">Device operating normally</div>
          <div className="text-[10px] text-emerald-600">No action required · Rules-based assessment</div>
        </div>
      </div>
    );
  }

  const borderColor = site.status === "Not Connected" ? "border-red-200 bg-red-50"
    : site.status === "Attention Needed" ? "border-amber-200 bg-amber-50"
    : "border-gray-200 bg-gray-50";

  const textColor = site.status === "Not Connected" ? "text-red-800"
    : site.status === "Attention Needed" ? "text-amber-800"
    : "text-gray-700";

  return (
    <div className={`${borderColor} border rounded-lg p-3`}>
      <div className="flex items-center gap-1.5 mb-2">
        <Zap className={`w-3.5 h-3.5 ${textColor}`} />
        <span className={`text-[10px] font-bold uppercase tracking-wide ${textColor}`}>Ops Assessment</span>
        <span className="ml-auto text-[9px] text-gray-400">Rules-based · not AI</span>
      </div>
      {issues.map((iss, i) => (
        <p key={i} className={`text-xs ${textColor} leading-relaxed mb-0.5`}>⚠ {iss}</p>
      ))}
      {nextSteps.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-200/50">
          <div className={`text-[10px] font-bold ${textColor} mb-1`}>NEXT STEPS</div>
          {nextSteps.map((s, i) => (
            <div key={i} className={`text-[11px] ${textColor} flex items-start gap-1`}>
              <span className="font-bold opacity-50 flex-shrink-0">{i + 1}.</span>{s}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}