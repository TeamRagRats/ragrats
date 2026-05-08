"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ReviewWidget from "@/components/ReviewWidget";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  queryId?: string;
}

export default function ChatBubble({ role, content, queryId }: ChatBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[75%] text-white text-base text-right whitespace-pre-wrap break-words">
          {content}
        </p>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="flex flex-col gap-2">
        <div className="max-w-[75%] text-white text-base break-words flex flex-col gap-2">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="whitespace-pre-wrap">{children}</p>,
              strong: ({ children }) => <strong className="font-bold text-white">{children}</strong>,
              em: ({ children }) => <em className="italic">{children}</em>,
              h1: ({ children }) => <h1 className="text-xl font-bold mt-2">{children}</h1>,
              h2: ({ children }) => <h2 className="text-lg font-bold mt-2">{children}</h2>,
              h3: ({ children }) => <h3 className="text-base font-bold mt-2">{children}</h3>,
              ul: ({ children }) => <ul className="list-disc pl-5 flex flex-col gap-1">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal pl-5 flex flex-col gap-1">{children}</ol>,
              li: ({ children }) => <li>{children}</li>,
              hr: () => <hr className="border-gray-700 my-2" />,
              code: ({ children }) => (
                <code className="bg-gray-900 px-1 py-0.5 rounded text-sm">{children}</code>
              ),
              pre: ({ children }) => (
                <pre className="bg-gray-900 p-2 rounded overflow-x-auto text-sm">{children}</pre>
              ),
              a: ({ href, children }) => (
                <a href={href} className="underline text-green-400" target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
        {queryId && <ReviewWidget queryId={queryId} />}
      </div>
    </div>
  );
}
