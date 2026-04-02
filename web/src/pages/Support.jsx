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
    </div>
  );
}
