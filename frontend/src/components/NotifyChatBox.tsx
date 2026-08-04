import React, { useState } from "react";
import { MessageSquare, X, Send, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

interface ChatMessage {
  id: string;
  text: string;
  sender: string;
  timestamp: string;
  status: "sending" | "sent" | "error";
  errorMessage?: string;
}

export const NotifyChatBox: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messageText, setMessageText] = useState("");
  const [senderName, setSenderName] = useState("Dashboard");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [bannerStatus, setBannerStatus] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = messageText.trim();
    if (!trimmed || isSubmitting) return;

    const msgId = Date.now().toString();
    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const newMsg: ChatMessage = {
      id: msgId,
      text: trimmed,
      sender: senderName.trim() || "Dashboard",
      timestamp: timeStr,
      status: "sending"
    };

    setMessages((prev) => [...prev, newMsg]);
    setMessageText("");
    setIsSubmitting(true);
    setBannerStatus(null);

    try {
      // Determine API endpoint URL
      const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
      const endpoint = `${backendUrl}/api/notify`;

      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: trimmed,
          sender: senderName.trim() || "Dashboard"
        })
      });

      if (!response.ok) {
        let errDetail = "Failed to send notification";
        try {
          const errJson = await response.json();
          if (errJson.detail) errDetail = errJson.detail;
        } catch {
          // ignore
        }
        throw new Error(errDetail);
      }

      // Success
      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, status: "sent" } : m))
      );
      setBannerStatus({ type: "success", text: "Sent ✓" });
      setTimeout(() => setBannerStatus(null), 3000);
    } catch (err: any) {
      const errMsg = err.message || "Failed to send — check connection";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, status: "error", errorMessage: errMsg } : m
        )
      );
      setBannerStatus({ type: "error", text: errMsg });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-40 select-none font-sans">
      {/* Floating collapsed chat button */}
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          aria-label="Open team notification chat"
          className="h-12 w-12 bg-gray-900 hover:bg-black text-white rounded-full
            flex items-center justify-center shadow-lg transition-all duration-150
            hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-900/50 cursor-pointer"
        >
          <MessageSquare className="h-5 w-5" />
        </button>
      )}

      {/* Expanded chat panel */}
      {isOpen && (
        <div
          className="w-80 sm:w-96 bg-white border border-gray-200 rounded-2xl shadow-xl
            flex flex-col overflow-hidden animate-fadeIn text-gray-900"
        >
          {/* Header */}
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-lg bg-gray-900 text-white flex items-center justify-center">
                <MessageSquare className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-gray-900 leading-tight">Notify Team</h3>
                <p className="text-[10px] text-gray-500">Sends review notes to Telegram</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close notification panel"
              className="p-1 hover:bg-gray-200 text-gray-400 hover:text-gray-600 rounded-md transition-colors cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Banner status alert */}
          {bannerStatus && (
            <div
              className={`px-3 py-1.5 text-xs font-medium flex items-center justify-between border-b ${
                bannerStatus.type === "success"
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : "bg-red-50 text-red-800 border-red-200"
              }`}
            >
              <span className="flex items-center gap-1.5 truncate">
                {bannerStatus.type === "success" ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                ) : (
                  <AlertCircle className="h-3.5 w-3.5 text-red-600 shrink-0" />
                )}
                <span>{bannerStatus.text}</span>
              </span>
              <button
                type="button"
                onClick={() => setBannerStatus(null)}
                className="text-gray-400 hover:text-gray-600 ml-2"
              >
                ×
              </button>
            </div>
          )}

          {/* Messages session list */}
          <div className="p-3 h-52 overflow-y-auto space-y-2.5 bg-gray-50/30">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 p-4">
                <MessageSquare className="h-8 w-8 text-gray-300 mb-1.5" />
                <p className="text-xs font-medium text-gray-500">No notes sent yet</p>
                <p className="text-[11px] text-gray-400 mt-0.5 max-w-[200px]">
                  Type a review note below to instantly notify your team in Telegram.
                </p>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className="bg-white border border-gray-200 rounded-xl p-2.5 shadow-xs space-y-1"
                >
                  <div className="flex items-center justify-between text-[10px] text-gray-500">
                    <span className="font-semibold text-gray-700">{msg.sender}</span>
                    <span className="font-mono">{msg.timestamp}</span>
                  </div>
                  <p className="text-xs text-gray-800 break-words leading-relaxed">{msg.text}</p>
                  <div className="flex items-center justify-end gap-1 text-[10px]">
                    {msg.status === "sending" && (
                      <span className="text-gray-400 flex items-center gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" /> Sending...
                      </span>
                    )}
                    {msg.status === "sent" && (
                      <span className="text-emerald-600 font-medium flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Sent ✓
                      </span>
                    )}
                    {msg.status === "error" && (
                      <span className="text-red-600 font-medium flex items-center gap-1" title={msg.errorMessage}>
                        <AlertCircle className="h-3 w-3" /> Failed
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Form / Inputs */}
          <form onSubmit={handleSend} className="p-3 border-t border-gray-200 bg-white space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Sender name"
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
                className="w-full text-[11px] bg-gray-50 border border-gray-200 rounded-lg px-2.5 py-1 text-gray-700
                  focus:outline-none focus:border-blue-500 font-medium"
              />
            </div>

            <div className="flex items-center gap-2">
              <textarea
                rows={2}
                placeholder="Type note for team... (e.g. This update is needed)"
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                className="flex-1 text-xs bg-gray-50 border border-gray-200 rounded-lg p-2 text-gray-900
                  placeholder-gray-400 focus:outline-none focus:border-blue-500 focus:bg-white
                  resize-none transition-all"
              />
              <button
                type="submit"
                disabled={!messageText.trim() || isSubmitting}
                aria-label="Send notification"
                className="h-9 w-9 bg-gray-900 hover:bg-black disabled:bg-gray-200 disabled:cursor-not-allowed
                  text-white rounded-lg flex items-center justify-center shrink-0 transition-colors shadow-xs cursor-pointer"
              >
                {isSubmitting ? (
                  <Loader2 className="h-4 w-4 animate-spin text-white" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};

export default NotifyChatBox;
