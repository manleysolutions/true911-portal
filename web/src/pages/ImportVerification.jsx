import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  ArrowLeft, Building2, Cpu, Phone, CheckCircle2, AlertTriangle,
  XCircle, Loader2, ChevronRight, Search, RefreshCw, Shield,
  ArrowRight, Merge, Edit3, ChevronDown, ChevronUp, Activity,
  FileSpreadsheet, Users,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";

const RECON_COLORS = {
  clean: "bg-emerald-100 text-emerald-700",
  verified: "bg-blue-100 text-blue-700",
  needs_review: "bg-amber-100 text-amber-700",
  incomplete: "bg-orange-100 text-orange-700",
  duplicate_suspected: "bg-red-100 text-red-700",
  imported_unverified: "bg-gray-100 text-gray-600",
};

const RECON_LABELS = {
  clean: "Clean",
  verified: "Verified",
  needs_review: "Needs Review",
  incomplete: "Incomplete",
  duplicate_suspected: "Dup Suspected",
  imported_unverified: "Unverified",
};

export default function ImportVerification() {
  const { can } = useAuth();
  const [view, setView] = useState("customers"); // customers | site | batches
  const [customers, setCustomers] = useState([]);
  const [batches, setBatches] = useState([]);
  const [selectedSite, setSelectedSite] = useState(null);
  const [siteDetail, setSiteDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [siteLoading, setSiteLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedCustomer, setExpandedCustomer] = useState(null);
  const [customerSites, setCustomerSites] = useState({});

  // Correction modals
  const [showReassignLine, setShowReassignLine] = useState(null);
  const [showReassignDevice, setShowReassignDevice] = useState(null);
  const [showMergeSites, setShowMergeSites] = useState(null);
  const [showEditLine, setShowEditLine] = useState(null);
  const [correctionInput, setCorrectionInput] = useState("");
  const [editLineForm, setEditLineForm] = useState({});

  const loadCustomers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/command/subscriber-import/verify");
      setCustomers(data);
    } catch (err) {
      toast.error("Failed to load verification data");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBatches = useCallback(async () => {
    try {
      const data = await apiFetch("/command/subscriber-import/batches");
      setBatches(data);
    } catch (err) {
      toast.error("Failed to load import batches");
    }
  }, []);

  useEffect(() => {
    loadCustomers();
    loadBatches();
  }, [loadCustomers, loadBatches]);

  const loadSiteDetail = async (siteId) => {
    setSiteLoading(true);
    try {
      const data = await apiFetch(`/command/subscriber-import/verify/site/${siteId}`);
      setSiteDetail(data);
      setSelectedSite(siteId);
      setView("site");
    } catch (err) {
      toast.error("Failed to load site detail");
    } finally {
      setSiteLoading(false);
    }
  };

  const loadCustomerSites = async (customerName) => {
    try {
      const sites = await apiFetch(`/command/subscriber-import/verify/customer-sites?customer_name=${encodeURIComponent(customerName)}`);
      setCustomerSites(prev => ({ ...prev, [customerName]: sites }));
    } catch {
      setCustomerSites(prev => ({ ...prev, [customerName]: [] }));
    }
  };

  const toggleCustomer = (customerName) => {
    if (expandedCustomer === customerName) {
      setExpandedCustomer(null);
    } else {
      setExpandedCustomer(customerName);
      if (!customerSites[customerName]) {
        loadCustomerSites(customerName);
      }
    }
  };

  // Correction actions
  const handleReassignLine = async () => {
    if (!showReassignLine || !correctionInput) return;
    try {
      await apiFetch("/command/subscriber-import/correct/reassign-line", {
        method: "POST",
        body: JSON.stringify({ line_id: showReassignLine, new_device_id: correctionInput }),
      });
      toast.success("Line reassigned");
      setShowReassignLine(null);
      setCorrectionInput("");
      if (selectedSite) loadSiteDetail(selectedSite);
    } catch (err) {
      toast.error(err.message || "Failed to reassign");
    }
  };

  const handleReassignDevice = async () => {
    if (!showReassignDevice || !correctionInput) return;
    try {
      await apiFetch("/command/subscriber-import/correct/reassign-device", {
        method: "POST",
        body: JSON.stringify({ device_id: showReassignDevice, new_site_id: correctionInput }),
      });
      toast.success("Device reassigned");
      setShowReassignDevice(null);
      setCorrectionInput("");
      if (selectedSite) loadSiteDetail(selectedSite);
    } catch (err) {
      toast.error(err.message || "Failed to reassign");
    }
  };

  const handleMergeSites = async (keepId) => {
    if (!showMergeSites || !keepId) return;
    const mergeId = showMergeSites === keepId ? null : showMergeSites;
    if (!mergeId) { toast.error("Cannot merge a site with itself"); return; }
    try {
      await apiFetch("/command/subscriber-import/correct/merge-sites", {
        method: "POST",
        body: JSON.stringify({ keep_site_id: keepId, merge_site_id: mergeId }),
      });
      toast.success("Sites merged");
      setShowMergeSites(null);
      setCorrectionInput("");
      loadCustomers();
    } catch (err) {
      toast.error(err.message || "Failed to merge");
    }
  };

  const handleUpdateRecon = async (entityType, entityId, newStatus) => {
    try {
      await apiFetch("/command/subscriber-import/correct/reconciliation", {
        method: "POST",
        body: JSON.stringify({ entity_type: entityType, entity_id: entityId, status: newStatus }),
      });
      toast.success(`Marked as ${newStatus}`);
      if (selectedSite) loadSiteDetail(selectedSite);
      loadCustomers();
    } catch (err) {
      toast.error(err.message || "Failed to update status");
    }
  };

  const handleEditLine = async () => {
    if (!showEditLine) return;
    try {
      await apiFetch(`/command/subscriber-import/correct/line/${showEditLine}`, {
        method: "PATCH",
        body: JSON.stringify(editLineForm),
      });
      toast.success("Line updated");
      setShowEditLine(null);
      setEditLineForm({});
      if (selectedSite) loadSiteDetail(selectedSite);
    } catch (err) {
      toast.error(err.message || "Failed to update line");
    }
  };

  if (!can("SUBSCRIBER_IMPORT")) {
    return (
      <PageWrapper>
        <div className="p-6 text-center text-gray-500">You do not have permission to access this page.</div>
      </PageWrapper>
    );
  }

  const filteredCustomers = customers.filter(c =>
    !searchTerm || c.customer_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <PageWrapper>
      <div className="p-6 max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          {view === "site" ? (
            <button onClick={() => setView("customers")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700">
              <ArrowLeft className="w-3.5 h-3.5" /> Back to Customers
            </button>
          ) : (
            <Link to={createPageUrl("SubscriberImport")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700">
              <ArrowLeft className="w-3.5 h-3.5" /> Back to Import
            </Link>
          )}
        </div>

        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-red-600" />
            <h1 className="text-2xl font-bold text-gray-900">Import Verification</h1>
          </div>
          <button onClick={() => { loadCustomers(); loadBatches(); }} className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700">
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>

        {/* View tabs */}
        <div className="flex gap-1 mb-4 border-b border-gray-200">
          <button
            onClick={() => setView("customers")}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px ${view === "customers" || view === "site" ? "border-red-600 text-red-600" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          >
            <Users className="w-3 h-3 inline mr-1" /> By Customer
          </button>
          <button
            onClick={() => setView("batches")}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px ${view === "batches" ? "border-red-600 text-red-600" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          >
            <FileSpreadsheet className="w-3 h-3 inline mr-1" /> Import History
          </button>
        </div>

        {/* CUSTOMER VIEW */}
        {(view === "customers") && (
          <>
            <div className="relative mb-4">
              <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                placeholder="Search customers..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg"
              />
            </div>

            {loading ? (
              <div className="text-center py-8"><Loader2 className="w-6 h-6 text-gray-400 animate-spin mx-auto" /></div>
            ) : filteredCustomers.length === 0 ? (
              <div className="text-center py-8 text-sm text-gray-400">
                No imported customers found. <Link to={createPageUrl("SubscriberImport")} className="text-red-600 hover:text-red-700">Run an import</Link> first.
              </div>
            ) : (
              <div className="space-y-3">
                {filteredCustomers.map(c => (
                  <div key={c.customer_id} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                    <div
                      className="p-4 cursor-pointer hover:bg-gray-50"
                      onClick={() => toggleCustomer(c.customer_name)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div>
                            <h3 className="text-sm font-semibold text-gray-900">{c.customer_name}</h3>
                            {c.customer_number && <p className="text-xs text-gray-400">{c.customer_number}</p>}
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="flex items-center gap-3 text-xs">
                            <span className="flex items-center gap-1 text-gray-500"><Building2 className="w-3 h-3" /> {c.sites}</span>
                            <span className="flex items-center gap-1 text-gray-500"><Cpu className="w-3 h-3" /> {c.devices}</span>
                            <span className="flex items-center gap-1 text-gray-500"><Phone className="w-3 h-3" /> {c.lines}</span>
                          </div>
                          <HealthBadge score={c.health_score} />
                          {c.unresolved_issues > 0 && (
                            <span className="flex items-center gap-1 text-xs text-amber-600">
                              <AlertTriangle className="w-3 h-3" /> {c.unresolved_issues}
                            </span>
                          )}
                          {expandedCustomer === c.customer_name ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                        </div>
                      </div>
                    </div>

                    {expandedCustomer === c.customer_name && (
                      <div className="border-t border-gray-100 p-4 bg-gray-50">
                        {customerSites[c.customer_name] ? (
                          customerSites[c.customer_name].length > 0 ? (
                            <div className="space-y-2">
                              {customerSites[c.customer_name].map(site => (
                                <div
                                  key={site.site_id}
                                  className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-100 hover:border-gray-300 cursor-pointer"
                                  onClick={() => loadSiteDetail(site.site_id)}
                                >
                                  <div>
                                    <p className="text-sm font-medium text-gray-900">{site.site_name}</p>
                                    <p className="text-xs text-gray-400">
                                      {[site.e911_street, site.e911_city, site.e911_state].filter(Boolean).join(", ") || "No address"}
                                    </p>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <ReconBadge status={site.reconciliation_status} />
                                    <ChevronRight className="w-4 h-4 text-gray-400" />
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-xs text-gray-400 text-center py-2">No sites found for this customer</p>
                          )
                        ) : (
                          <div className="text-center py-2"><Loader2 className="w-4 h-4 text-gray-400 animate-spin mx-auto" /></div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* SITE DETAIL VIEW */}
        {view === "site" && (
          <>
            {siteLoading ? (
              <div className="text-center py-8"><Loader2 className="w-6 h-6 text-gray-400 animate-spin mx-auto" /></div>
            ) : siteDetail ? (
              <div className="space-y-4">
                {/* Site header */}
                <div className="bg-white border border-gray-200 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h2 className="text-lg font-bold text-gray-900">{siteDetail.site_name}</h2>
                      <p className="text-xs text-gray-500">{siteDetail.customer_name} — {siteDetail.site_id}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <ReconBadge status={siteDetail.reconciliation_status} />
                      <ReconDropdown
                        currentStatus={siteDetail.reconciliation_status}
                        onSelect={(s) => handleUpdateRecon("site", siteDetail.site_id, s)}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-600">
                    <div><span className="text-gray-400">Address:</span> {siteDetail.address || "—"}</div>
                    <div><span className="text-gray-400">City:</span> {siteDetail.city || "—"}</div>
                    <div><span className="text-gray-400">State:</span> {siteDetail.state || "—"}</div>
                    <div><span className="text-gray-400">ZIP:</span> {siteDetail.zip || "—"}</div>
                  </div>
                </div>

                {/* Devices */}
                {siteDetail.devices.map(device => (
                  <div key={device.device_id} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                    <div className="p-4 border-b border-gray-100">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                            <Cpu className="w-4 h-4 text-violet-500" />
                            {device.device_type || "Device"} — {device.device_id}
                          </p>
                          <div className="flex gap-3 text-xs text-gray-500 mt-1">
                            {device.imei && <span>IMEI: {device.imei}</span>}
                            {device.carrier && <span>Carrier: {device.carrier}</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <ReconBadge status={device.reconciliation_status} />
                          <ReconDropdown
                            currentStatus={device.reconciliation_status}
                            onSelect={(s) => handleUpdateRecon("device", device.device_id, s)}
                          />
                          <button
                            onClick={() => { setShowReassignDevice(device.device_id); setCorrectionInput(""); }}
                            className="text-[10px] text-blue-600 hover:text-blue-700 px-1.5 py-0.5 border border-blue-200 rounded"
                            title="Move device to another site"
                          >
                            Move
                          </button>
                        </div>
                      </div>
                      {/* Warnings */}
                      {device.warnings.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {device.warnings.map((w, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-xs text-amber-600">
                              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" /> {w}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Lines under device */}
                    {device.lines.length > 0 ? (
                      <div className="divide-y divide-gray-50">
                        {device.lines.map(line => (
                          <div key={line.line_id} className="px-4 py-3 flex items-center justify-between hover:bg-gray-50">
                            <div className="flex items-center gap-3">
                              <Phone className="w-3.5 h-3.5 text-amber-500" />
                              <div>
                                <p className="text-xs font-medium text-gray-900">{line.did || "No MSISDN"}</p>
                                <div className="flex gap-2 text-[10px] text-gray-400">
                                  {line.sim_iccid && <span>SIM: {line.sim_iccid}</span>}
                                  {line.carrier && <span>Carrier: {line.carrier}</span>}
                                  {line.line_type && <span>Type: {line.line_type}</span>}
                                  {line.qb_description && <span>QB: {line.qb_description}</span>}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <ReconBadge status={line.reconciliation_status} />
                              <ReconDropdown
                                currentStatus={line.reconciliation_status}
                                onSelect={(s) => handleUpdateRecon("line", line.line_id, s)}
                              />
                              <button
                                onClick={() => { setShowEditLine(line.line_id); setEditLineForm({ did: line.did || "", sim_iccid: line.sim_iccid || "", carrier: line.carrier || "", line_type: line.line_type || "", qb_description: line.qb_description || "" }); }}
                                className="text-[10px] text-gray-500 hover:text-gray-700 px-1.5 py-0.5 border border-gray-200 rounded"
                              >
                                <Edit3 className="w-2.5 h-2.5" />
                              </button>
                              <button
                                onClick={() => { setShowReassignLine(line.line_id); setCorrectionInput(""); }}
                                className="text-[10px] text-blue-600 hover:text-blue-700 px-1.5 py-0.5 border border-blue-200 rounded"
                                title="Move line to another device"
                              >
                                Move
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="px-4 py-3 text-xs text-gray-400 italic">No lines under this device</div>
                    )}
                  </div>
                ))}

                {/* Orphan lines */}
                {siteDetail.orphan_lines.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                    <p className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4" /> Orphan Lines (no device assigned)
                    </p>
                    <div className="space-y-2">
                      {siteDetail.orphan_lines.map(line => (
                        <div key={line.line_id} className="flex items-center justify-between p-2 bg-white rounded-lg">
                          <div className="text-xs">
                            <span className="font-medium">{line.did || "No MSISDN"}</span>
                            {line.sim_iccid && <span className="text-gray-400 ml-2">SIM: {line.sim_iccid}</span>}
                          </div>
                          <button
                            onClick={() => { setShowReassignLine(line.line_id); setCorrectionInput(""); }}
                            className="text-[10px] text-blue-600 hover:text-blue-700 px-1.5 py-0.5 border border-blue-200 rounded"
                          >
                            Assign to Device
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-center text-gray-400 py-8">Site not found</p>
            )}
          </>
        )}

        {/* BATCH HISTORY VIEW */}
        {view === "batches" && (
          <div className="space-y-3">
            {batches.length === 0 ? (
              <p className="text-center text-gray-400 py-8 text-sm">No import batches yet</p>
            ) : batches.map(b => (
              <div key={b.batch_id} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">{b.batch_id}</p>
                    <p className="text-xs text-gray-400">{b.file_name || "Unknown file"} — {b.created_by}</p>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    b.status === "committed" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"
                  }`}>
                    {b.status}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                  <div><span className="text-gray-400">Total Rows:</span> {b.total_rows || 0}</div>
                  <div><span className="text-gray-400">Lines:</span> {b.lines_created || 0}</div>
                  <div><span className="text-gray-400">Devices:</span> {b.devices_created || 0}</div>
                  <div><span className="text-gray-400">Sites:</span> {b.sites_created || 0}</div>
                  <div><span className="text-gray-400">Failed:</span> {b.rows_failed || 0}</div>
                </div>
                {b.committed_at && <p className="text-[10px] text-gray-400 mt-1">Committed: {new Date(b.committed_at).toLocaleString()}</p>}
              </div>
            ))}
          </div>
        )}

        {/* CORRECTION MODALS */}

        {/* Reassign Line */}
        {showReassignLine && (
          <Modal title="Reassign Line to Device" onClose={() => setShowReassignLine(null)}>
            <p className="text-xs text-gray-500 mb-3">Line: {showReassignLine}</p>
            <label className="text-xs font-medium text-gray-700">Target Device ID</label>
            <input
              type="text"
              value={correctionInput}
              onChange={(e) => setCorrectionInput(e.target.value)}
              placeholder="DEV-XXXXXXXX"
              className="w-full mt-1 px-3 py-2 text-sm border border-gray-200 rounded-lg"
            />
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowReassignLine(null)} className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg">Cancel</button>
              <button onClick={handleReassignLine} disabled={!correctionInput} className="flex-1 px-3 py-2 text-sm bg-red-600 text-white rounded-lg disabled:opacity-60">Reassign</button>
            </div>
          </Modal>
        )}

        {/* Reassign Device */}
        {showReassignDevice && (
          <Modal title="Move Device to Site" onClose={() => setShowReassignDevice(null)}>
            <p className="text-xs text-gray-500 mb-3">Device: {showReassignDevice}</p>
            <label className="text-xs font-medium text-gray-700">Target Site ID</label>
            <input
              type="text"
              value={correctionInput}
              onChange={(e) => setCorrectionInput(e.target.value)}
              placeholder="SITE-XXXXXXXX"
              className="w-full mt-1 px-3 py-2 text-sm border border-gray-200 rounded-lg"
            />
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowReassignDevice(null)} className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg">Cancel</button>
              <button onClick={handleReassignDevice} disabled={!correctionInput} className="flex-1 px-3 py-2 text-sm bg-red-600 text-white rounded-lg disabled:opacity-60">Move</button>
            </div>
          </Modal>
        )}

        {/* Edit Line */}
        {showEditLine && (
          <Modal title="Edit Line Details" onClose={() => setShowEditLine(null)}>
            <p className="text-xs text-gray-500 mb-3">Line: {showEditLine}</p>
            <div className="space-y-2">
              <FieldInput label="Phone (MSISDN)" value={editLineForm.did || ""} onChange={(v) => setEditLineForm({...editLineForm, did: v})} />
              <FieldInput label="SIM ICCID" value={editLineForm.sim_iccid || ""} onChange={(v) => setEditLineForm({...editLineForm, sim_iccid: v})} />
              <FieldInput label="Carrier" value={editLineForm.carrier || ""} onChange={(v) => setEditLineForm({...editLineForm, carrier: v})} />
              <FieldInput label="Line Type" value={editLineForm.line_type || ""} onChange={(v) => setEditLineForm({...editLineForm, line_type: v})} />
              <FieldInput label="QB Description" value={editLineForm.qb_description || ""} onChange={(v) => setEditLineForm({...editLineForm, qb_description: v})} />
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowEditLine(null)} className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg">Cancel</button>
              <button onClick={handleEditLine} className="flex-1 px-3 py-2 text-sm bg-red-600 text-white rounded-lg">Save</button>
            </div>
          </Modal>
        )}
      </div>
    </PageWrapper>
  );
}

function HealthBadge({ score }) {
  let color = "bg-emerald-100 text-emerald-700";
  if (score < 50) color = "bg-red-100 text-red-700";
  else if (score < 80) color = "bg-amber-100 text-amber-700";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {score}%
    </span>
  );
}

function ReconBadge({ status }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${RECON_COLORS[status] || RECON_COLORS.imported_unverified}`}>
      {RECON_LABELS[status] || status || "—"}
    </span>
  );
}

function ReconDropdown({ currentStatus, onSelect }) {
  const [open, setOpen] = useState(false);
  const options = ["clean", "needs_review", "incomplete", "duplicate_suspected", "imported_unverified", "verified"];
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="text-[10px] text-gray-400 hover:text-gray-600 px-1">
        <ChevronDown className="w-2.5 h-2.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-5 z-50 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[140px]">
          {options.map(s => (
            <button
              key={s}
              onClick={() => { onSelect(s); setOpen(false); }}
              className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 ${s === currentStatus ? "font-semibold" : ""}`}
            >
              <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${RECON_COLORS[s]?.split(" ")[0] || "bg-gray-200"}`} />
              {RECON_LABELS[s]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-[70] flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-gray-900 mb-3">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function FieldInput({ label, value, onChange }) {
  return (
    <div>
      <label className="text-[10px] font-medium text-gray-500 uppercase">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-0.5 px-2 py-1.5 text-xs border border-gray-200 rounded-lg"
      />
    </div>
  );
}
