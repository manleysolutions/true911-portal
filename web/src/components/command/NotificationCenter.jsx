import { useState, useEffect, useCallback, useRef } from "react";
import { Bell, X, Check, CheckCheck, AlertOctagon, AlertTriangle, Info } from "lucide-react";
import { apiFetch } from "@/api/client";

const SEV_ICON = {
  critical: { icon: AlertOctagon, cls: "text-red-400" },
  warning:  { icon: AlertTriangle, cls: "text-amber-400" },
  info:     { icon: Info, cls: "text-blue-400" },
};

function timeSince(iso) {
  if (!iso) return "--";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function NotificationCenter({ unreadCount: externalCount }) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(externalCount || 0);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Sync external count
  useEffect(() => {
    if (externalCount !== undefined) setUnread(externalCount);
  }, [externalCount]);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/command/notifications?limit=20");
      setNotifications(data);
      setUnread(data.filter(n => !n.read).length);
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleOpen = () => {
    setOpen(o => !o);
    if (!open) fetchNotifications();
  };

  const markRead = async (ids) => {
    try {
      await apiFetch("/command/notifications/read", {
        method: "POST",
        body: JSON.stringify({ notification_ids: ids }),
      });
      setNotifications(prev => prev.map(n => ids.includes(n.id) ? { ...n, read: true } : n));
      setUnread(prev => Math.max(0, prev - ids.length));
    } catch (err) {
      console.error("Failed to mark read:", err);
    }
  };

  const markAllRead = async () => {
    try {
      await apiFetch("/command/notifications/read-all", { method: "POST" });
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnread(0);
    } catch (err) {
      console.error("Failed to mark all read:", err);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={handleOpen}
        className="relative p-2 rounded-lg border border-slate-700/50 hover:bg-slate-800 text-slate-400 transition-colors"
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-600 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 bg-slate-900 border border-slate-700/50 rounded-xl shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
            <h4 className="text-sm font-semibold text-white">Notifications</h4>
            <div className="flex items-center gap-2">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-200 font-medium"
                >
                  <CheckCheck className="w-3 h-3" /> Mark all read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="text-slate-500 hover:text-slate-300">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="max-h-[400px] overflow-y-auto divide-y divide-slate-800/50">
            {loading && notifications.length === 0 && (
              <div className="px-4 py-8 text-center">
                <div className="w-4 h-4 border-2 border-red-500 border-t-transparent rounded-full animate-spin mx-auto" />
              </div>
            )}
            {!loading && notifications.length === 0 && (
              <div className="px-4 py-8 text-center text-sm text-slate-600">No notifications</div>
            )}
            {notifications.map((n) => {
              const sev = SEV_ICON[n.severity] || SEV_ICON.info;
              const Icon = sev.icon;
              return (
                <div
                  key={n.id}
                  className={`flex items-start gap-3 px-4 py-3 transition-colors ${
                    n.read ? "opacity-60" : "hover:bg-slate-800/50"
                  }`}
                >
                  <Icon className={`w-4 h-4 flex-shrink-0 mt-0.5 ${sev.cls}`} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm leading-snug ${n.read ? "text-slate-400" : "text-slate-200"}`}>
                      {n.title}
                    </p>
                    {n.body && (
                      <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{n.body}</p>
                    )}
                    <span className="text-[10px] text-slate-600 mt-1 block">{timeSince(n.created_at)}</span>
                  </div>
                  {!n.read && (
                    <button
                      onClick={() => markRead([n.id])}
                      className="p-1 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 flex-shrink-0"
                      title="Mark read"
                    >
                      <Check className="w-3 h-3" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
