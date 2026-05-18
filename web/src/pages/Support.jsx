/**
 * Support — customer-facing support page.
 *
 * Provides:
 *   - Service status summary (operational / attention / impacted)
 *   - AI chat assistant
 *   - System test with simplified results
 *   - Human help request
 *
 * All language is calm, simple, and non-technical.
 * No raw diagnostics, incidents, or internal details are shown.
 */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import {
  PhoneCall,
  ShieldAlert,
  Cpu,
  MapPin,
  Mail,
  Clock,
} from "lucide-react";

import CustomerSupportHeader, { deriveOverallStatus } from "@/components/support/CustomerSupportHeader";
import CustomerSupportChat from "@/components/support/CustomerSupportChat";
import CustomerStatusCard from "@/components/support/CustomerStatusCard";
import CustomerNextStepCard from "@/components/support/CustomerNextStepCard";
import CustomerHelpRequestCard from "@/components/support/CustomerHelpRequestCard";
import CustomerSystemTestResult from "@/components/support/CustomerSystemTestResult";

export default function Support() {
  const { user } = useAuth();

  // ── State ──
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);

  const [overallStatus, setOverallStatus] = useState("operational");
  const [lastChecked, setLastChecked] = useState(null);
  const [recommendedActions, setRecommendedActions] = useState([]);

  const [testVisible, setTestVisible] = useState(false);
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const [helpLoading, setHelpLoading] = useState(false);
  const [error, setError] = useState(null);

  // ── Create session on mount ──
  useEffect(() => {
    createSession();
  }, []);

  const createSession = async () => {
    try {
      const data = await apiFetch("/support/sessions", {
        method: "POST",
        body: JSON.stringify({}),
      });
      setSessionId(data.id);

      // Fetch the greeting message
      const detail = await apiFetch(`/support/sessions/${data.id}`);
      setMessages(
        (detail.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        }))
      );
    } catch (err) {
      setError("We're unable to start a support session right now. Please try again in a moment.");
    }
  };

  // ── Send message ──
  const handleSendMessage = useCallback(async (text) => {
    if (!sessionId || sending) return;

    // Optimistic user message
    const tempId = `temp-${Date.now()}`;
    setMessages((prev) => [...prev, { id: tempId, role: "user", content: text }]);
    setSending(true);
    setError(null);

    try {
      const resp = await apiFetch(`/support/sessions/${sessionId}/message`, {
        method: "POST",
        body: JSON.stringify({ content: text }),
      });

      // Extract only customer-safe content
      const assistantContent = resp.structured_response?.customer_response || resp.content;
      const actions = resp.structured_response?.recommended_actions || [];

      setMessages((prev) => [
        ...prev,
        { id: resp.id, role: "assistant", content: assistantContent },
      ]);

      if (actions.length > 0) setRecommendedActions(actions);

      // Auto-escalation notification
      if (resp.structured_response?.escalate) {
        toast("Our assistant has flagged this for team review.", { duration: 5000 });
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: "I'm sorry, I wasn't able to process that. Please try again or request human help.",
        },
      ]);
    }
    setSending(false);
  }, [sessionId, sending]);

  // ── Run system test ──
  const handleRunTest = useCallback(async () => {
    if (!sessionId) return;

    setTestVisible(true);
    setTestRunning(true);
    setTestResult(null);

    try {
      const diagnostics = await apiFetch("/support/diagnostics/run", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId }),
      });

      // Map to simplified status (never expose raw data)
      const status = deriveOverallStatus(diagnostics);
      setOverallStatus(status);
      setTestResult(status);
      setLastChecked(new Date().toISOString());

      // Add a system-test chat message
      const resultMessages = {
        operational: "I just ran a system check — everything looks good. Your devices are reporting in normally.",
        attention: "I ran a system check and found something that may need attention. It's not necessarily a problem, but worth keeping an eye on.",
        impacted: "I ran a system check and wasn't able to confirm everything is working as expected. I'd recommend connecting with our support team.",
      };

      setMessages((prev) => [
        ...prev,
        {
          id: `test-${Date.now()}`,
          role: "assistant",
          content: resultMessages[status] || resultMessages.operational,
        },
      ]);
    } catch (err) {
      setTestResult("operational"); // Graceful fallback
      setMessages((prev) => [
        ...prev,
        {
          id: `test-err-${Date.now()}`,
          role: "assistant",
          content: "I wasn't able to complete the system check right now. You can try again in a moment or contact our support team.",
        },
      ]);
    }

    setTestRunning(false);
  }, [sessionId]);

  // ── Request human help ──
  const handleRequestHelp = useCallback(async () => {
    if (!sessionId) return;
    setHelpLoading(true);

    try {
      await apiFetch("/support/escalate", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          reason: "Customer requested human support",
        }),
      });

      setMessages((prev) => [
        ...prev,
        {
          id: `esc-${Date.now()}`,
          role: "assistant",
          content:
            "Your support request has been submitted. We've included the checks already completed so you don't have to repeat anything. Our team will follow up shortly.",
        },
      ]);
    } catch (err) {
      toast.error("We weren't able to submit your request. Please try again.");
    }

    setHelpLoading(false);
  }, [sessionId]);

  // ── Chat about test results ──
  const handleChatAboutResults = () => {
    handleSendMessage("Can you tell me more about my system test results?");
  };

  // ── Error fallback ──
  if (error && !sessionId) {
    return (
      <div className="max-w-lg mx-auto mt-16 text-center px-4">
        <div className="bg-white rounded-xl border border-gray-200 p-8">
          <p className="text-sm text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => { setError(null); createSession(); }}
            className="text-sm font-medium text-red-600 hover:text-red-700"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
      {/* ── Status Header ── */}
      <CustomerSupportHeader
        overallStatus={overallStatus}
        lastChecked={lastChecked}
      />

      {/* ── Main Body: 2-column ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* LEFT: Chat (takes 2 cols on desktop) */}
        <div className="lg:col-span-2" style={{ minHeight: "480px" }}>
          <CustomerSupportChat
            messages={messages}
            onSendMessage={handleSendMessage}
            onRunTest={handleRunTest}
            onRequestHelp={handleRequestHelp}
            sending={sending}
          />
        </div>

        {/* RIGHT: Context cards */}
        <div className="space-y-4">
          <CustomerStatusCard status={overallStatus} />

          <CustomerNextStepCard
            actions={recommendedActions}
            onSendMessage={handleSendMessage}
          />

          <CustomerSystemTestResult
            visible={testVisible}
            running={testRunning}
            result={testResult}
            onRunAgain={handleRunTest}
            onChatAbout={handleChatAboutResults}
            onRequestHelp={handleRequestHelp}
          />

          <CustomerHelpRequestCard
            onRequestHelp={handleRequestHelp}
            loading={helpLoading}
          />
        </div>
      </div>

      {/* ── Help Center ─────────────────────────────────────────────
          Static, read-only enterprise help cards.  Identical for
          every authenticated user; no role gating and no backend
          calls.  Each card surfaces an existing way to reach the
          True911 team — none of them introduces a new workflow. */}
      <HelpCenter />
    </div>
  );
}


// ──────────────────────────────────────────────────────────────────
// Help Center — static enterprise support cards
// ──────────────────────────────────────────────────────────────────

function HelpCenter() {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Help Center</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Reach the True911 team for support, emergency assistance, and deployment changes.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <HelpCard
          icon={PhoneCall}
          title="Contact Support"
          body="Reach our customer success team for account, billing, and general portal questions."
          rows={[
            { icon: PhoneCall, label: "(888) 911-TRUE" },
            { icon: Mail, label: "support@true911.com" },
            { icon: Clock, label: "24/7 — replies within one business day" },
          ]}
        />
        <HelpCard
          icon={ShieldAlert}
          title="Emergency Assistance"
          body="For a life-threatening emergency at a site, dial 911 directly. For portal or platform emergencies, contact our on-call line."
          tone="warning"
          rows={[
            { icon: ShieldAlert, label: "Dial 911 for any life-safety emergency" },
            { icon: PhoneCall, label: "(888) 911-TRUE — platform on-call" },
          ]}
        />
        <HelpCard
          icon={Cpu}
          title="Device Information Requests"
          body="Need specifications, deployment history, or carrier details for a device? Submit a request and our team will respond with the records on file."
          rows={[
            { icon: Mail, label: "devices@true911.com" },
            { icon: Clock, label: "Most requests answered within 1–2 business days" },
          ]}
        />
        <HelpCard
          icon={MapPin}
          title="E911 Update Requests"
          body="Updates to registered E911 addresses are processed by True911 operations to keep your compliance records accurate."
          rows={[
            { icon: Mail, label: "e911@true911.com" },
            { icon: Clock, label: "Address changes typically reflected within 1–3 business days" },
          ]}
        />
      </div>
    </section>
  );
}

function HelpCard({ icon: Icon, title, body, rows = [], tone = "neutral" }) {
  const accent =
    tone === "warning"
      ? "bg-amber-50 text-amber-600 border-amber-200"
      : "bg-slate-50 text-slate-600 border-slate-200";
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <div className={`w-9 h-9 rounded-lg border ${accent} flex items-center justify-center flex-shrink-0`}>
          <Icon className="w-4 h-4" />
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <p className="text-[13px] text-slate-600 mt-1 leading-relaxed">{body}</p>
        </div>
      </div>
      {rows.length > 0 && (
        <div className="pl-12 space-y-1.5">
          {rows.map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-[13px] text-slate-700">
              <r.icon className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
              <span>{r.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
