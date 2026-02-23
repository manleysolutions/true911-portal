import { useState, useEffect, useCallback } from "react";
import { NotificationRule } from "@/api/entities";
import { Bell, Plus, Trash2, RefreshCw, ChevronDown, ChevronUp, Shield, AlertTriangle, Phone, Mail, MessageSquare, Edit2, Check, X } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const RULE_TYPES = [
  { value: "offline_timeout", label: "Device Offline Timeout", desc: "Trigger when device not seen for X minutes", defaultThreshold: 30, defaultUnit: "minutes" },
  { value: "missed_heartbeat", label: "Missed Heartbeat", desc: "Trigger when scheduled heartbeat is not received", defaultThreshold: 1, defaultUnit: "days" },
  { value: "sip_unregistered", label: "SIP Unregistered", desc: "Trigger when SIP registration fails", defaultThreshold: 1, defaultUnit: "minutes" },
  { value: "signal_below_threshold", label: "Signal Below Threshold", desc: "Trigger when RSSI drops below value", defaultThreshold: -85, defaultUnit: "dbm" },
  { value: "power_event", label: "Power / AC Failure", desc: "Trigger on AC power loss or battery low", defaultThreshold: 20, defaultUnit: "percent" },
  { value: "battery_low", label: "Battery Low", desc: "Trigger when battery below threshold", defaultThreshold: 15, defaultUnit: "percent" },
  { value: "container_unhealthy", label: "Container Unhealthy", desc: "Trigger when health score drops below threshold", defaultThreshold: 40, defaultUnit: "percent" },
];

const CONTACT_ROLES = [
  { value: "security", label: "Security Team", icon: "🔒" },
  { value: "site_owner", label: "Site Owner / POC", icon: "🏢" },
  { value: "psap", label: "PSAP Coordinator", icon: "🚨" },
  { value: "admin", label: "Portal Admin", icon: "⚙️" },
];

const CHANNEL_ICONS = {
  email: { icon: Mail, label: "Email", color: "text-blue-600" },
  sms: { icon: MessageSquare, label: "SMS", color: "text-green-600" },
  portal: { icon: Bell, label: "Portal Alert", color: "text-purple-600" },
};

function EscalationStep({ step, onChange, onDelete }) {
  return (
    <div className="flex items-start gap-2 bg-gray-50 rounded-lg p-3 border border-gray-100">
      <div className="w-6 h-6 rounded-full bg-gray-800 text-white text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-bold">{step.step}</div>
      <div className="flex-1 grid grid-cols-2 gap-2">
        <div>
          <label className="text-[10px] text-gray-500 font-medium block mb-0.5">Role</label>
          <select
            value={step.contact_role}
            onChange={e => onChange({ ...step, contact_role: e.target.value })}
            className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            {CONTACT_ROLES.map(r => (
              <option key={r.value} value={r.value}>{r.icon} {r.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[10px] text-gray-500 font-medium block mb-0.5">Delay (min)</label>
          <input
            type="number"
            value={step.delay_minutes}
            onChange={e => onChange({ ...step, delay_minutes: parseInt(e.target.value) || 0 })}
            className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-red-500"
          />
        </div>
        <div>
          <label className="text-[10px] text-gray-500 font-medium block mb-0.5">Contact Email</label>
          <input
            value={step.contact_email || ''}
            onChange={e => onChange({ ...step, contact_email: e.target.value })}
            placeholder="e.g. security@org.com"
            className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-red-500"
          />
        </div>
        <div>
          <label className="text-[10px] text-gray-500 font-medium block mb-0.5">Contact Phone</label>
          <input
            value={step.contact_phone || ''}
            onChange={e => onChange({ ...step, contact_phone: e.target.value })}
            placeholder="e.g. +1-555-0100"
            className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-red-500"
          />
        </div>
      </div>
      <button onClick={onDelete} className="p-1 text-gray-400 hover:text-red-500 flex-shrink-0">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

function RuleCard({ rule, onUpdate, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const rt = RULE_TYPES.find(r => r.value === rule.rule_type);

  const toggleEnabled = async () => {
    await NotificationRule.update(rule.id, { enabled: !rule.enabled });
    onUpdate();
    toast.success(`Rule "${rule.rule_name}" ${rule.enabled ? 'disabled' : 'enabled'}.`);
  };

  const handleDelete = async () => {
    await NotificationRule.delete(rule.id);
    onUpdate();
    toast.success('Rule deleted.');
  };

  return (
    <div className={`bg-white rounded-xl border transition-all ${rule.enabled ? 'border-gray-200' : 'border-gray-100 opacity-60'}`}>
      <div className="flex items-center gap-3 p-4">
        <button
          onClick={toggleEnabled}
          className={`w-9 h-5 rounded-full relative transition-colors flex-shrink-0 ${rule.enabled ? 'bg-emerald-500' : 'bg-gray-200'}`}
        >
          <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${rule.enabled ? 'left-4' : 'left-0.5'}`} />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-900">{rule.rule_name}</span>
            <span className="text-[10px] font-medium bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{rt?.label || rule.rule_type}</span>
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-xs text-gray-500">Threshold: <strong>{rule.threshold_value} {rule.threshold_unit}</strong></span>
            <span className="text-xs text-gray-500">Scope: <strong>{rule.scope?.replace('_', ' ')}</strong></span>
            {rule.channels?.map(ch => {
              const c = CHANNEL_ICONS[ch];
              if (!c) return null;
              const Icon = c.icon;
              return <Icon key={ch} className={`w-3 h-3 ${c.color}`} title={c.label} />;
            })}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {rule.last_triggered && (
            <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-100">
              Last triggered: {new Date(rule.last_triggered).toLocaleDateString()}
            </span>
          )}
          <button onClick={() => setExpanded(v => !v)} className="p-1.5 rounded-lg hover:bg-gray-50 text-gray-400">
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button onClick={handleDelete} className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-50 pt-3">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Escalation Ladder</div>
          {rule.escalation_steps?.length > 0 ? (
            <div className="space-y-2">
              {rule.escalation_steps.map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
                  <div className="w-5 h-5 rounded-full bg-gray-700 text-white text-[10px] flex items-center justify-center font-bold">{step.step}</div>
                  <span className="font-medium text-gray-800">{CONTACT_ROLES.find(r => r.value === step.contact_role)?.label || step.contact_role}</span>
                  <span className="text-gray-400">·</span>
                  <span>+{step.delay_minutes}min</span>
                  {step.contact_email && <span className="text-gray-400 truncate">{step.contact_email}</span>}
                  {step.contact_phone && <span className="text-gray-400">{step.contact_phone}</span>}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-gray-400 italic">No escalation steps defined.</div>
          )}
          <div className="mt-2 text-[10px] text-gray-400">
            ⚠ Notifications are simulated in demo mode. Connect SMS/email APIs to enable real delivery.
          </div>
        </div>
      )}
    </div>
  );
}

const DEFAULT_RULE = {
  rule_name: '',
  rule_type: 'offline_timeout',
  threshold_value: 30,
  threshold_unit: 'minutes',
  scope: 'all_sites',
  channels: ['portal'],
  escalation_steps: [],
  enabled: true,
  tenant_id: 'demo',
};

function NewRuleForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({ ...DEFAULT_RULE });
  const [saving, setSaving] = useState(false);

  const setRuleType = (rt) => {
    const def = RULE_TYPES.find(r => r.value === rt);
    setForm(f => ({ ...f, rule_type: rt, threshold_value: def?.defaultThreshold ?? 0, threshold_unit: def?.defaultUnit ?? 'minutes' }));
  };

  const toggleChannel = (ch) => {
    setForm(f => ({
      ...f,
      channels: f.channels.includes(ch) ? f.channels.filter(c => c !== ch) : [...f.channels, ch],
    }));
  };

  const addStep = () => {
    const step = form.escalation_steps.length + 1;
    const delays = [0, 15, 60];
    const roles = ['security', 'site_owner', 'psap'];
    setForm(f => ({
      ...f,
      escalation_steps: [...f.escalation_steps, {
        step,
        delay_minutes: delays[Math.min(step - 1, 2)],
        contact_role: roles[Math.min(step - 1, 2)],
        contact_email: '',
        contact_phone: '',
      }]
    }));
  };

  const updateStep = (i, updated) => {
    setForm(f => ({ ...f, escalation_steps: f.escalation_steps.map((s, idx) => idx === i ? updated : s) }));
  };

  const deleteStep = (i) => {
    setForm(f => ({ ...f, escalation_steps: f.escalation_steps.filter((_, idx) => idx !== i).map((s, idx) => ({ ...s, step: idx + 1 })) }));
  };

  const handleSave = async () => {
    if (!form.rule_name) { toast.error('Rule name is required.'); return; }
    if (form.channels.length === 0) { toast.error('Select at least one notification channel.'); return; }
    setSaving(true);
    await NotificationRule.create({
      ...form,
      rule_id: `RULE-${Date.now()}`,
      trigger_count: 0,
    });
    setSaving(false);
    toast.success('Notification rule created.');
    onCreated();
  };

  return (
    <div className="bg-white rounded-xl border border-red-200 p-5 mb-5">
      <div className="flex items-center gap-2 mb-5">
        <Bell className="w-4 h-4 text-red-600" />
        <h3 className="font-semibold text-gray-900">New Notification Rule</h3>
        <button onClick={onCancel} className="ml-auto text-gray-400 hover:text-gray-600 p-1"><X className="w-4 h-4" /></button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">Rule Name</label>
          <input
            value={form.rule_name}
            onChange={e => setForm(f => ({ ...f, rule_name: e.target.value }))}
            placeholder="e.g. Life Safety Offline Alert"
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">Rule Type</label>
          <select
            value={form.rule_type}
            onChange={e => setRuleType(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            {RULE_TYPES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
          <div className="text-[10px] text-gray-400 mt-0.5">{RULE_TYPES.find(r => r.value === form.rule_type)?.desc}</div>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">Threshold</label>
          <div className="flex gap-2">
            <input
              type="number"
              value={form.threshold_value}
              onChange={e => setForm(f => ({ ...f, threshold_value: parseFloat(e.target.value) }))}
              className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
            <select
              value={form.threshold_unit}
              onChange={e => setForm(f => ({ ...f, threshold_unit: e.target.value }))}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            >
              {['minutes', 'hours', 'days', 'dbm', 'percent'].map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 block mb-1">Scope</label>
          <select
            value={form.scope}
            onChange={e => setForm(f => ({ ...f, scope: e.target.value }))}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            <option value="all_sites">All Sites</option>
            <option value="life_safety_only">Life Safety Only</option>
            <option value="specific_sites">Specific Sites</option>
          </select>
        </div>
      </div>

      <div className="mb-4">
        <label className="text-xs font-medium text-gray-600 block mb-2">Notification Channels</label>
        <div className="flex gap-2">
          {Object.entries(CHANNEL_ICONS).map(([key, { icon: Icon, label, color }]) => (
            <button
              key={key}
              onClick={() => toggleChannel(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                form.channels.includes(key) ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 text-gray-600 hover:border-gray-400'
              }`}
            >
              <Icon className="w-3 h-3" /> {label}
            </button>
          ))}
        </div>
        <div className="text-[10px] text-gray-400 mt-1">SMS and email are simulated — connect API keys to enable real delivery.</div>
      </div>

      <div className="mb-5">
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-medium text-gray-600">Escalation Ladder</label>
          <button onClick={addStep} className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700 font-medium">
            <Plus className="w-3 h-3" /> Add Step
          </button>
        </div>
        {form.escalation_steps.length === 0 && (
          <div className="text-xs text-gray-400 italic py-2">No escalation steps. Click "Add Step" to define Step 1 (security), Step 2 (owner), Step 3 (PSAP).</div>
        )}
        <div className="space-y-2">
          {form.escalation_steps.map((step, i) => (
            <EscalationStep key={i} step={step} onChange={u => updateStep(i, u)} onDelete={() => deleteStep(i)} />
          ))}
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <button onClick={onCancel} className="px-4 py-2 text-sm text-gray-700 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white font-medium rounded-lg transition-colors"
        >
          {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          {saving ? 'Saving...' : 'Create Rule'}
        </button>
      </div>
    </div>
  );
}

export default function Notifications() {
  const { can } = useAuth();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const fetchData = useCallback(async () => {
    const data = await NotificationRule.list('-created_date', 100);
    setRules(data);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (!can('MANAGE_NOTIFICATIONS')) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-4xl mb-3">🔒</div>
            <div className="text-lg font-semibold text-gray-800">Admin Access Required</div>
            <div className="text-sm text-gray-500 mt-1">Notification rule management requires Admin access.</div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Notifications & Escalation</h1>
            <p className="text-sm text-gray-500 mt-0.5">Configure life-safety alert rules and escalation ladders</p>
          </div>
          <div className="flex gap-2">
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
            {!showForm && (
              <button
                onClick={() => setShowForm(true)}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Plus className="w-4 h-4" /> New Rule
              </button>
            )}
          </div>
        </div>

        {/* Info banner */}
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-semibold text-amber-800">Demo Mode — Simulated Notifications</div>
            <div className="text-xs text-amber-700 mt-0.5">
              Notification rules are stored and displayed, but delivery (SMS, email) is simulated.
              Connect carrier SMS API and SMTP provider to enable real escalation.
            </div>
          </div>
        </div>

        {/* New rule form */}
        {showForm && (
          <NewRuleForm
            onCreated={() => { setShowForm(false); fetchData(); }}
            onCancel={() => setShowForm(false)}
          />
        )}

        {/* Rules list */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : rules.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-gray-300 py-16 text-center">
            <Bell className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <div className="text-sm font-semibold text-gray-500">No notification rules yet</div>
            <div className="text-xs text-gray-400 mt-1">Click "New Rule" to configure your first alert.</div>
          </div>
        ) : (
          <div className="space-y-3">
            {rules.map(rule => (
              <RuleCard key={rule.id} rule={rule} onUpdate={fetchData} onDelete={fetchData} />
            ))}
          </div>
        )}
      </div>
    </PageWrapper>
  );
}