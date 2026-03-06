import { Users, Phone, Mail, Wrench } from "lucide-react";

const CATEGORY_LABELS = {
  fire_alarm: "Fire Alarm",
  elevator_phone: "Elevator Phone",
  das_radio: "DAS / Radio",
  call_station: "Call Station",
  backup_power: "Backup Power",
  other: "Other",
};

export default function VendorAssignments({ assignments = [] }) {
  if (assignments.length === 0) {
    return (
      <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/50">
          <Users className="w-4 h-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-white">Vendor Assignments</h3>
        </div>
        <div className="px-5 py-6 text-center text-sm text-slate-600">
          No vendors assigned
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/50">
        <Users className="w-4 h-4 text-purple-400" />
        <h3 className="text-sm font-semibold text-white">Vendor Assignments</h3>
        <span className="text-xs text-slate-500">{assignments.length}</span>
      </div>
      <div className="divide-y divide-slate-800/50">
        {assignments.map((a) => (
          <div key={a.id} className="px-5 py-3">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <Wrench className="w-3 h-3 text-slate-600" />
                <span className="text-xs text-slate-500 font-semibold uppercase">
                  {CATEGORY_LABELS[a.system_category] || a.system_category}
                </span>
                {a.is_primary && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    PRIMARY
                  </span>
                )}
              </div>
            </div>
            <p className="text-sm text-slate-200 font-medium">{a.vendor_name || "Unknown"}</p>
            <div className="flex items-center gap-4 mt-1">
              {a.vendor_contact_name && (
                <span className="text-xs text-slate-500">{a.vendor_contact_name}</span>
              )}
              {a.vendor_contact_phone && (
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Phone className="w-3 h-3" />{a.vendor_contact_phone}
                </span>
              )}
              {a.vendor_contact_email && (
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Mail className="w-3 h-3" />{a.vendor_contact_email}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
