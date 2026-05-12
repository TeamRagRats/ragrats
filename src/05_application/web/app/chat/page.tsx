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
  queryId?: string;
}

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
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
        { id: newId(), role: "user", content: text },
      ]);
      setLoading(true);

      try {
        const { answer, queryId } = await sendMessage(text, sessionId);
        setMessages((prev) => [
          ...prev,
          { id: newId(), role: "assistant", content: answer, queryId },
        ]);
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) => [
          ...prev,
          { id: newId(), role: "assistant", content: `Error: ${errMsg}` },
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

  function handleNewQuestion() {
    setMessages([]);
  }

  const showInput = messages.length === 0;
  const showNewQuestion = messages.length > 0 && !loading;

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <p className="text-white text-sm">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-black">
      <header className="flex items-center justify-end gap-3 px-6 py-4 flex-shrink-0">
        <button
          onClick={() => router.push("/voyages?from=chat")}
          className="border-2 border-gray-600 bg-black text-white px-5 py-2 text-base hover:border-green-600 hover:text-green-400 transition-colors"
        >
          Voyages
        </button>
        <button
          onClick={handleLogout}
          className="border-2 border-gray-600 bg-black text-white px-5 py-2 text-base hover:border-green-600 hover:text-green-400 transition-colors"
        >
          Logout
        </button>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 py-4 pb-24 flex flex-col gap-6 items-center"
      >
        <div className="w-full max-w-4xl flex flex-col gap-6">
          {messages.length === 0 && !loading && (
            <p className="text-gray-600 text-sm mt-16">_</p>
          )}
          {messages.map((msg) => (
            <ChatBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              queryId={msg.queryId}
            />
          ))}
          {loading && <LoadingBubble />}
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 bg-black">
        {showInput && (
          <MessageInput onSend={handleSend} disabled={loading || !sessionId} />
        )}
        {showNewQuestion && (
          <div className="w-full max-w-6xl mx-auto flex justify-center px-6 py-4 bg-black">
            <button
              onClick={handleNewQuestion}
              className="border-2 bg-black text-white text-xl px-10 py-5 transition-colors hover:text-green-400 animate-glow-pulse"
            >
              New Question
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
