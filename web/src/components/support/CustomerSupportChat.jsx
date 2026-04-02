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
    <div className="flex flex-col h-full bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Chat header */}
      <div className="px-4 py-3 border-b border-gray-100 bg-gray-50/50">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-red-50 rounded-full flex items-center justify-center">
            <Bot className="w-4 h-4 text-red-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-800">Support Assistant</h3>
            <p className="text-[10px] text-gray-400">Ask a question or choose an option below</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[200px]">
        {(!messages || messages.length === 0) && !sending && (
          <div className="text-center py-8">
            <Bot className="w-8 h-8 text-gray-200 mx-auto mb-2" />
            <p className="text-sm text-gray-400">How can I help you today?</p>
            <p className="text-xs text-gray-300 mt-1">Type a message or use the quick actions below.</p>
          </div>
        )}

        {messages?.map((msg) => (
          <ChatBubble key={msg.id} msg={msg} />
        ))}

        {sending && (
          <div className="flex items-start gap-2">
            <div className="w-6 h-6 bg-gray-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
              <Bot className="w-3.5 h-3.5 text-gray-500" />
            </div>
            <div className="bg-gray-50 rounded-xl rounded-tl-sm px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <Loader2 className="w-3.5 h-3.5 text-gray-400 animate-spin" />
                <span className="text-xs text-gray-400">Thinking...</span>
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
      <form onSubmit={handleSend} className="px-3 py-2.5 border-t border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your question..."
            disabled={sending}
            className="flex-1 text-sm px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-red-500 focus:bg-white disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || sending}
            className="w-9 h-9 bg-red-600 hover:bg-red-700 disabled:bg-gray-300 text-white rounded-lg flex items-center justify-center transition-colors"
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
        isUser ? "bg-blue-100" : "bg-gray-100"
      }`}>
        {isUser
          ? <User className="w-3.5 h-3.5 text-blue-600" />
          : <Bot className="w-3.5 h-3.5 text-gray-500" />
        }
      </div>
      <div className={`max-w-[80%] rounded-xl px-3 py-2.5 ${
        isUser
          ? "bg-blue-600 text-white rounded-tr-sm"
          : "bg-gray-50 text-gray-700 rounded-tl-sm border border-gray-100"
      }`}>
        <p className={`text-sm leading-relaxed whitespace-pre-wrap ${isUser ? "text-white" : "text-gray-700"}`}>
          {msg.content}
        </p>
      </div>
    </div>
  );
}
