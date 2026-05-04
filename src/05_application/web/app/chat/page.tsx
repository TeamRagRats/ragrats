"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import ChatBubble from "@/components/ChatBubble";
import LoadingBubble from "@/components/LoadingBubble";
import MessageInput from "@/components/MessageInput";
import { createSession, logout, sendMessage } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    async function init() {
      try {
        const res = await fetch("/api/health", { credentials: "include" });
        if (res.status === 401) {
          router.replace("/login");
          return;
        }
        const sid = await createSession();
        setSessionId(sid);
        setAuthChecked(true);
      } catch {
        router.replace("/login");
      }
    }
    init();
  }, [router]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!sessionId || loading) return;

      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: text },
      ]);
      setLoading(true);

      try {
        const answer = await sendMessage(text, sessionId);
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", content: answer },
        ]);
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", content: `Error: ${errMsg}` },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [sessionId, loading]
  );

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <p className="text-white text-sm">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-black">
      <header className="flex items-center justify-end px-6 py-4 flex-shrink-0">
        <button
          onClick={handleLogout}
          className="border border-gray-600 bg-black text-white px-3 py-1 rounded text-sm hover:border-green-600 hover:text-green-400 transition-colors"
        >
          Logout
        </button>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 py-4 pb-24 flex flex-col gap-6 items-center"
      >
        <div className="w-full max-w-xl flex flex-col gap-6">
          {messages.length === 0 && !loading && (
            <p className="text-gray-600 text-sm mt-16">_</p>
          )}
          {messages.map((msg) => (
            <ChatBubble key={msg.id} role={msg.role} content={msg.content} />
          ))}
          {loading && <LoadingBubble />}
        </div>
      </div>

      <div className="fixed bottom-4 left-1/2 -translate-x-1/2">
        <MessageInput onSend={handleSend} disabled={loading || !sessionId} />
      </div>
    </div>
  );
}
