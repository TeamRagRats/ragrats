"use client";

import ReviewWidget from "@/components/ReviewWidget";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  queryId?: string;
  generationId?: string;
}

export default function ChatBubble({ role, content, queryId, generationId }: ChatBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[75%] text-white text-sm text-right whitespace-pre-wrap break-words">
          {content}
        </p>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="flex flex-col gap-2">
        <p className="max-w-[75%] text-white text-sm whitespace-pre-wrap break-words">
          {content}
        </p>
        {queryId && <ReviewWidget queryId={queryId} generationId={generationId ?? null} />}
      </div>
    </div>
  );
}
