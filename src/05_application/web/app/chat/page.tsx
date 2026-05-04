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
      <div className="min-h-screen flex items-center justify-center bg-white">
        <p className="text-black text-sm">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-white">
      <header className="flex items-center justify-between border-b border-black px-6 py-4 flex-shrink-0">
        <h1 className="text-xl font-bold text-black tracking-tight">RagRats</h1>
        <button
          onClick={handleLogout}
          className="text-sm border border-black text-black px-3 py-1.5 rounded hover:bg-black hover:text-white transition-colors"
        >
          Log out
        </button>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-6 flex flex-col gap-4"
      >
        {messages.length === 0 && !loading && (
          <p className="text-center text-gray-400 text-sm mt-16">
            Ask anything about the project…
          </p>
        )}
        {messages.map((msg) => (
          <ChatBubble key={msg.id} role={msg.role} content={msg.content} />
        ))}
        {loading && <LoadingBubble />}
      </div>

      <div className="flex-shrink-0">
        <MessageInput onSend={handleSend} disabled={loading || !sessionId} />
      </div>
    </div>
  );
}
