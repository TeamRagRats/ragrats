"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import ChatBubble from "@/components/ChatBubble";
import LoadingBubble from "@/components/LoadingBubble";
import MessageInput from "@/components/MessageInput";
import { createSession, logout, streamMessage } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  // Check auth and create a session on mount
  useEffect(() => {
    async function init() {
      try {
        // A lightweight auth check — if the cookie is gone the session creation will 401
        const res = await fetch("/api/health", { credentials: "include" });
        if (res.status === 401) {
          router.replace("/login");
          return;
        }
        const sid = await createSession();
        setSessionId(sid);
        setAuthChecked(true);
      } catch {
        // createSession returning 401 also lands here
        router.replace("/login");
      }
    }
    init();
  }, [router]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!sessionId || streaming) return;

      const userMsgId = crypto.randomUUID();
      const assistantMsgId = crypto.randomUUID();

      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: "user", content: text },
      ]);
      setStreaming(true);

      // Add a placeholder assistant message that we'll fill token by token
      setMessages((prev) => [
        ...prev,
        { id: assistantMsgId, role: "assistant", content: "" },
      ]);

      try {
        await streamMessage(
          text,
          sessionId,
          (token) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: m.content + token }
                  : m
              )
            );
          },
          () => {
            setStreaming(false);
          }
        );
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: `Error: ${errMsg}` }
              : m
          )
        );
        setStreaming(false);
      }
    },
    [sessionId, streaming]
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
      {/* Header */}
      <header className="flex items-center justify-between border-b border-black px-6 py-4 flex-shrink-0">
        <h1 className="text-xl font-bold text-black tracking-tight">RagRats</h1>
        <button
          onClick={handleLogout}
          className="text-sm border border-black text-black px-3 py-1.5 rounded hover:bg-black hover:text-white transition-colors"
        >
          Log out
        </button>
      </header>

      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-6 flex flex-col gap-4"
      >
        {messages.length === 0 && (
          <p className="text-center text-gray-400 text-sm mt-16">
            Ask anything about the project…
          </p>
        )}
        {messages.map((msg) =>
          msg.role === "assistant" && msg.content === "" && streaming ? (
            <LoadingBubble key={msg.id} />
          ) : (
            <ChatBubble key={msg.id} role={msg.role} content={msg.content} />
          )
        )}
      </div>

      {/* Input */}
      <div className="flex-shrink-0">
        <MessageInput onSend={handleSend} disabled={streaming || !sessionId} />
      </div>
    </div>
  );
}
