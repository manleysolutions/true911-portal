import { useState, useEffect, useCallback } from "react";
import { Line, Site } from "@/api/entities";
import { Phone, Search, RefreshCw, Plus, X, CheckCircle2 } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";

const STATUS_BADGE = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  provisioning: "bg-blue-50 text-blue-700 border-blue-200",
  suspended: "bg-amber-50 text-amber-700 border-amber-200",
  disconnected: "bg-red-50 text-red-700 border-red-200",
};

const E911_BADGE = {
  validated: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  none: "bg-gray-100 text-gray-500 border-gray-200",
};

function AddLineModal({ onClose, onCreated, sites }) {
  const [form, setForm] = useState({
    line_id: "", provider: "telnyx", did: "", sip_uri: "",
    protocol: "SIP", site_id: "", device_id: "",
    e911_street: "", e911_city: "", e911_state: "", e911_zip: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await Line.create({
        ...form,
        sip_uri: form.sip_uri || undefined,
        site_id: form.site_id || undefined,
        device_id: form.device_id || undefined,
        e911_street: form.e911_street || undefined,
        e911_city: form.e911_city || undefined,
        e911_state: form.e911_state || undefined,
        e911_zip: form.e911_zip || undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err?.message || "Failed to create line.");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Phone className="w-4 h-4 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">Add Voice Line</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Line ID *</label>
              <input value={form.line_id} onChange={set("line_id")} required
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="e.g. LINE-001" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">DID / Phone *</label>
              <input value={form.did} onChange={set("did")} required
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="+12145550101" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Provider</label>
              <select value={form.provider} onChange={set("provider")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                <option value="telnyx">Telnyx</option>
                <option value="tmobile">T-Mobile</option>
                <option value="bandwidth">Bandwidth</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Protocol</label>
              <select value={form.protocol} onChange={set("protocol")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                <option value="SIP">SIP</option>
                <option value="POTS">POTS</option>
                <option value="cellular">Cellular</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Site</label>
              <select value={form.site_id} onChange={set("site_id")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent">
                <option value="">-- None --</option>
                {sites.map(s => <option key={s.site_id} value={s.site_id}>{s.site_name}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">SIP URI</label>
            <input value={form.sip_uri} onChange={set("sip_uri")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              placeholder="sip:2145550101@sip.telnyx.com" />
          </div>

          <div className="border-t border-gray-100 pt-4">
            <div className="text-xs font-semibold text-gray-600 mb-2 uppercase tracking-wide">E911 Address</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <input value={form.e911_street} onChange={set("e911_street")} placeholder="Street"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent" />
              </div>
              <input value={form.e911_city} onChange={set("e911_city")} placeholder="City"
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent" />
              <div className="flex gap-2">
                <input value={form.e911_state} onChange={set("e911_state")} placeholder="ST" maxLength={2}
                  className="w-20 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent uppercase" />
                <input value={form.e911_zip} onChange={set("e911_zip")} placeholder="ZIP"
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent" />
              </div>
            </div>
          </div>

          {error && <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">{error}</div>}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">Cancel</button>
            <button type="submit" disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
              {saving ? "Creating..." : "Add Line"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Lines() {
  const [lines, setLines] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const fetchData = useCallback(async () => {
    const [lineData, siteData] = await Promise.all([
      Line.list("-created_at", 200),
      Site.list("-last_checkin", 200),
    ]);
    setLines(lineData);
    setSites(siteData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const siteMap = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const filtered = lines.filter(l => {
    if (statusFilter && l.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const site = siteMap[l.site_id];
      return (
        l.line_id.toLowerCase().includes(q) ||
        (l.did || "").toLowerCase().includes(q) ||
        (l.provider || "").toLowerCase().includes(q) ||
        (site?.site_name || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Lines</h1>
            <p className="text-sm text-gray-500 mt-0.5">{lines.length} voice lines / DIDs</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowAdd(true)}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors">
              <Plus className="w-4 h-4" /> Add Line
            </button>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search lines, DID, provider, site..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="provisioning">Provisioning</option>
            <option value="suspended">Suspended</option>
            <option value="disconnected">Disconnected</option>
          </select>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Phone className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <div className="text-sm font-semibold text-gray-500">
                {lines.length === 0 ? "No voice lines yet" : "No lines match your filters"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {lines.length === 0 ? "Click \"Add Line\" to provision your first voice line." : "Try adjusting your search or filter."}
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Line ID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">DID</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Site</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Provider</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Protocol</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">E911</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(l => {
                  const site = siteMap[l.site_id];
                  return (
                    <tr key={l.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{l.line_id}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-800 font-semibold">{l.did || "---"}</td>
                      <td className="px-4 py-2.5 text-gray-800">{site?.site_name || l.site_id || "---"}</td>
                      <td className="px-4 py-2.5 text-gray-600 capitalize">{l.provider}</td>
                      <td className="px-4 py-2.5 text-gray-600">{l.protocol}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[l.status] || STATUS_BADGE.disconnected}`}>
                          {l.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${E911_BADGE[l.e911_status] || E911_BADGE.none}`}>
                          {l.e911_status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showAdd && (
        <AddLineModal
          sites={sites}
          onClose={() => setShowAdd(false)}
          onCreated={fetchData}
        />
      )}
    </PageWrapper>
  );
}
