import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Building2, ArrowLeft, Save, Loader2, Palette,
  Mail, Phone, Globe, Users, FileText, Webhook,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";

function Section({ title, icon: Icon, children }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
        <Icon className="w-4 h-4 text-gray-500" />
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text" }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-600 mb-1 uppercase tracking-wide">{label}</label>
      <input type={type} value={value || ""} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500" />
    </div>
  );
}

export default function OrgSettings() {
  const { user, can } = useAuth();
  const [org, setOrg] = useState(null);
  const [children, setChildren] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [orgData, childData, whData, ctData] = await Promise.all([
        apiFetch("/command/org"),
        apiFetch("/command/org/children").catch(() => []),
        can("COMMAND_MANAGE_WEBHOOKS") ? apiFetch("/command/outbound-webhooks").catch(() => []) : [],
        can("COMMAND_VIEW_CONTRACTS") ? apiFetch("/command/contracts").catch(() => []) : [],
      ]);
      setOrg(orgData);
      setChildren(childData);
      setWebhooks(whData);
      setContracts(ctData);
    } catch (err) {
      console.error("Failed to load org settings:", err);
    } finally {
      setLoading(false);
    }
  }, [can]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await apiFetch("/command/org", {
        method: "PUT",
        body: JSON.stringify({
          display_name: org.display_name,
          logo_url: org.logo_url,
          primary_color: org.primary_color,
          contact_email: org.contact_email,
          contact_phone: org.contact_phone,
        }),
      });
      setOrg(updated);
      toast.success("Organization settings saved");
    } catch (err) {
      toast.error(err.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  const updateOrg = (field, val) => setOrg(prev => ({ ...prev, [field]: val }));

  return (
    <PageWrapper>
      <div className="p-6 max-w-3xl mx-auto space-y-6">
        <Link to={createPageUrl("Admin")} className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Settings
        </Link>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-red-600" />
            <h1 className="text-2xl font-bold text-gray-900">Organization Settings</h1>
          </div>
          {can("VIEW_ADMIN") && (
            <button onClick={handleSave} disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white rounded-xl text-sm font-semibold">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Changes
            </button>
          )}
        </div>

        {/* Organization Info */}
        <Section title="Organization Details" icon={Globe}>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <div className="flex items-center gap-3 mb-4 p-3 bg-gray-50 rounded-lg">
                <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center text-red-600 font-bold">
                  {(org?.display_name || org?.name || "?").charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{org?.name}</p>
                  <p className="text-xs text-gray-500">ID: {org?.tenant_id} &middot; Type: {org?.org_type}</p>
                </div>
              </div>
            </div>
            <Field label="Display Name" value={org?.display_name} onChange={v => updateOrg("display_name", v)} placeholder="Public-facing name" />
            <Field label="Logo URL" value={org?.logo_url} onChange={v => updateOrg("logo_url", v)} placeholder="https://..." />
            <Field label="Contact Email" value={org?.contact_email} onChange={v => updateOrg("contact_email", v)} placeholder="admin@company.com" type="email" />
            <Field label="Contact Phone" value={org?.contact_phone} onChange={v => updateOrg("contact_phone", v)} placeholder="+1-555-000-0000" />
          </div>
        </Section>

        {/* Branding */}
        <Section title="Branding" icon={Palette}>
          <div className="flex items-center gap-4">
            <Field label="Primary Color" value={org?.primary_color} onChange={v => updateOrg("primary_color", v)} placeholder="#DC2626" />
            {org?.primary_color && (
              <div className="mt-5 w-10 h-10 rounded-lg border border-gray-200" style={{ backgroundColor: org.primary_color }} />
            )}
          </div>
        </Section>

        {/* Child Organizations (MSP) */}
        {children.length > 0 && (
          <Section title="Managed Organizations" icon={Users}>
            <div className="space-y-2">
              {children.map(child => (
                <div key={child.tenant_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{child.display_name || child.name}</p>
                    <p className="text-xs text-gray-500">{child.tenant_id} &middot; {child.org_type}</p>
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${child.is_active ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
                    {child.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Outbound Webhooks */}
        {can("COMMAND_MANAGE_WEBHOOKS") && (
          <Section title="Outbound Webhooks" icon={Webhook}>
            {webhooks.length === 0 ? (
              <p className="text-sm text-gray-500">No outbound webhooks configured.</p>
            ) : (
              <div className="space-y-2">
                {webhooks.map(wh => (
                  <div key={wh.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{wh.name}</p>
                      <p className="text-xs text-gray-500 font-mono truncate max-w-[300px]">{wh.url}</p>
                    </div>
                    <div className="text-right">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${wh.enabled ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>
                        {wh.enabled ? "Active" : "Disabled"}
                      </span>
                      {wh.failure_count > 0 && (
                        <p className="text-[10px] text-red-500 mt-0.5">{wh.failure_count} failures</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        {/* Service Contracts */}
        {can("COMMAND_VIEW_CONTRACTS") && contracts.length > 0 && (
          <Section title="Service Contracts" icon={FileText}>
            <div className="space-y-2">
              {contracts.map(c => (
                <div key={c.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{c.vendor_name || `Vendor #${c.vendor_id}`}</p>
                    <p className="text-xs text-gray-500">{c.contract_type} &middot; SLA: {c.sla_response_minutes}min response, {c.sla_resolution_hours}h resolution</p>
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    c.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"
                  }`}>
                    {c.status}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </PageWrapper>
  );
}
