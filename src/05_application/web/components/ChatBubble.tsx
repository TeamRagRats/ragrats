"use client";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
}

export default function ChatBubble({ role, content }: ChatBubbleProps) {
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
      <p className="max-w-[75%] text-white text-sm whitespace-pre-wrap break-words">
        {content}
      </p>
    </div>
  );
}
