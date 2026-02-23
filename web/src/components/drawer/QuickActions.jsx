import { useState } from "react";
import { Radio, Power, MapPin, AlertOctagon, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { pingDevice, rebootDevice } from "../actions";
import { toast } from "sonner";

const ACTION_STATES = {
  idle: null,
  queued: "Queued",
  sent: "Sent",
  acknowledged: "Acknowledged",
  completed: "Completed",
  failed: "Failed",
};

export default function QuickActions({ site, onSiteUpdated, onOpenE911, onCreateIncident }) {
  const { user, can } = useAuth();
  const [pingState, setPingState] = useState("idle");
  const [rebootState, setRebootState] = useState("idle");
  const [showRebootConfirm, setShowRebootConfirm] = useState(false);

  const handlePing = async () => {
    if (!can("PING")) return;
    setPingState("queued");
    await new Promise(r => setTimeout(r, 300));
    setPingState("sent");
    await new Promise(r => setTimeout(r, 400));
    setPingState("acknowledged");
    const result = await pingDevice(user, site);
    setPingState(result.success ? "completed" : "failed");
    if (result.success) toast.success(result.message);
    else toast.error(result.message);
    onSiteUpdated?.();
    setTimeout(() => setPingState("idle"), 3000);
  };

  const handleReboot = async () => {
    if (!can("REBOOT")) return;
    setShowRebootConfirm(false);
    setRebootState("queued");
    await new Promise(r => setTimeout(r, 400));
    setRebootState("sent");
    await rebootDevice(user, site);
    setRebootState("acknowledged");
    await new Promise(r => setTimeout(r, 600));
    setRebootState("completed");
    toast.success("Reboot initiated. Device will return online within ~45 seconds.");
    onSiteUpdated?.();
    setTimeout(() => setRebootState("idle"), 4000);
  };

  const stateLabel = (state) => ACTION_STATES[state] || null;
  const isActive = (state) => state !== "idle";

  const stateColor = (state) => {
    if (state === "failed") return "text-red-600 bg-red-50 border-red-200";
    if (state === "completed") return "text-emerald-700 bg-emerald-50 border-emerald-200";
    if (isActive(state)) return "text-blue-700 bg-blue-50 border-blue-200";
    return "";
  };

  return (
    <div className="mb-4">
      <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Quick Actions</div>
      <div className="grid grid-cols-2 gap-2">
        {/* Ping */}
        <div>
          <button
            onClick={handlePing}
            disabled={!can("PING") || isActive(pingState)}
            title={!can("PING") ? "Requires Manager or Admin role" : ""}
            className={`w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border text-xs font-semibold transition-all ${
              !can("PING")
                ? "bg-gray-50 text-gray-300 border-gray-100 cursor-not-allowed"
                : isActive(pingState)
                ? stateColor(pingState) + " border cursor-wait"
                : "bg-white text-gray-700 border-gray-200 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
            }`}
          >
            {isActive(pingState) && pingState !== "completed" && pingState !== "failed"
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Radio className="w-3.5 h-3.5" />
            }
            {isActive(pingState) ? stateLabel(pingState) : "Ping Device"}
          </button>
        </div>

        {/* Reboot */}
        <div>
          {showRebootConfirm ? (
            <div className="flex gap-1">
              <button
                onClick={handleReboot}
                className="flex-1 px-2 py-2.5 rounded-lg border text-xs font-semibold bg-red-600 text-white border-red-600 hover:bg-red-700 transition-colors"
              >Confirm</button>
              <button
                onClick={() => setShowRebootConfirm(false)}
                className="flex-1 px-2 py-2.5 rounded-lg border text-xs font-semibold bg-white text-gray-600 border-gray-200 hover:bg-gray-50 transition-colors"
              >Cancel</button>
            </div>
          ) : (
            <button
              onClick={() => can("REBOOT") && setShowRebootConfirm(true)}
              disabled={!can("REBOOT") || isActive(rebootState)}
              title={!can("REBOOT") ? "Requires Admin role" : ""}
              className={`w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border text-xs font-semibold transition-all ${
                !can("REBOOT")
                  ? "bg-gray-50 text-gray-300 border-gray-100 cursor-not-allowed"
                  : isActive(rebootState)
                  ? stateColor(rebootState) + " border cursor-wait"
                  : "bg-white text-gray-700 border-gray-200 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700"
              }`}
            >
              {isActive(rebootState) && rebootState !== "completed" && rebootState !== "failed"
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <Power className="w-3.5 h-3.5" />
              }
              {isActive(rebootState) ? stateLabel(rebootState) : "Reboot CSA"}
            </button>
          )}
        </div>

        {/* Update E911 */}
        <button
          onClick={can("UPDATE_E911") ? onOpenE911 : undefined}
          disabled={!can("UPDATE_E911")}
          title={!can("UPDATE_E911") ? "Requires Admin role" : ""}
          className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border text-xs font-semibold transition-all ${
            !can("UPDATE_E911")
              ? "bg-gray-50 text-gray-300 border-gray-100 cursor-not-allowed"
              : "bg-white text-gray-700 border-gray-200 hover:border-purple-300 hover:bg-purple-50 hover:text-purple-700"
          }`}
        >
          <MapPin className="w-3.5 h-3.5" />
          Update E911
        </button>

        {/* Create Incident */}
        <button
          onClick={can("ACK_INCIDENT") ? onCreateIncident : undefined}
          disabled={!can("ACK_INCIDENT")}
          title={!can("ACK_INCIDENT") ? "Requires Manager or Admin role" : ""}
          className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border text-xs font-semibold transition-all ${
            !can("ACK_INCIDENT")
              ? "bg-gray-50 text-gray-300 border-gray-100 cursor-not-allowed"
              : "bg-white text-gray-700 border-gray-200 hover:border-red-300 hover:bg-red-50 hover:text-red-700"
          }`}
        >
          <AlertOctagon className="w-3.5 h-3.5" />
          Create Incident
        </button>
      </div>
    </div>
  );
}