import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import CustomerQuickActions from "./CustomerQuickActions";

export default function CustomerSupportChat({
  messages,
  onSendMessage,
  onRunTest,
  onRequestHelp,
  sending,
}) {
  const [input, setInput] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages?.length, sending]);

  const handleSend = (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    onSendMessage(text);
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-slate-200 overflow-hidden">
      {/* Chat header */}
      <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/60">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-slate-800 rounded-full flex items-center justify-center">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Support Assistant</h3>
            <p className="text-[10.5px] text-slate-500 mt-0.5">Ask a question or choose an option below</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[200px]">
        {(!messages || messages.length === 0) && !sending && (
          <div className="text-center py-8">
            <Bot className="w-8 h-8 text-slate-200 mx-auto mb-2" />
            <p className="text-sm text-slate-400">How can I help you today?</p>
            <p className="text-xs text-slate-300 mt-1">Type a message or use the quick actions below.</p>
          </div>
        )}

        {messages?.map((msg) => (
          <ChatBubble key={msg.id} msg={msg} />
        ))}

        {sending && (
          <div className="flex items-start gap-2">
            <div className="w-6 h-6 bg-slate-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
              <Bot className="w-3.5 h-3.5 text-slate-500" />
            </div>
            <div className="bg-slate-50 rounded-xl rounded-tl-sm px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 text-slate-400 animate-spin" />
                <span className="text-xs text-slate-500">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Quick actions */}
      <CustomerQuickActions
        onSendMessage={onSendMessage}
        onRunTest={onRunTest}
        onRequestHelp={onRequestHelp}
      />

      {/* Input */}
      <form onSubmit={handleSend} className="px-3 py-2.5 border-t border-slate-200 bg-white">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your question..."
            disabled={sending}
            className="flex-1 text-sm px-3 py-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-400 focus:bg-white disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            aria-label="Send message"
            className="w-9 h-9 bg-slate-800 hover:bg-slate-900 disabled:bg-slate-300 text-white rounded-lg flex items-center justify-center transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
}

function ChatBubble({ msg }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex items-start gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
        isUser ? "bg-blue-100" : "bg-slate-100"
      }`}>
        {isUser
          ? <User className="w-3.5 h-3.5 text-blue-600" />
          : <Bot className="w-3.5 h-3.5 text-slate-500" />
        }
      </div>
      <div className={`max-w-[80%] rounded-xl px-3 py-2.5 ${
        isUser
          ? "bg-blue-600 text-white rounded-tr-sm"
          : "bg-slate-50 rounded-tl-sm border border-slate-100"
      }`}>
        <p className={`text-sm leading-relaxed whitespace-pre-wrap ${isUser ? "text-white" : "text-slate-700"}`}>
          {msg.content}
        </p>
      </div>
    </div>
  );
}
