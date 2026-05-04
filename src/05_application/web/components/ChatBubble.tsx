"use client";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
}

export default function ChatBubble({ role, content }: ChatBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-lg border border-black bg-white px-4 py-3 text-black text-sm whitespace-pre-wrap break-words">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] rounded-lg bg-black px-4 py-3 text-white text-sm whitespace-pre-wrap break-words">
        {content}
      </div>
    </div>
  );
}
