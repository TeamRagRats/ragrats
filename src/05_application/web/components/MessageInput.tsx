"use client";

import { useRef, useState } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${e.target.scrollHeight}px`;
  }

  return (
    <div className="w-full max-w-3xl flex items-start gap-3 px-4 py-3 bg-black">
      <span className="shrink-0 text-gray-500 text-sm pt-1 select-none">Question:</span>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder="Ask something…"
        className="flex-1 bg-transparent text-white text-sm placeholder-gray-700 caret-white resize-none overflow-hidden focus:outline-none disabled:opacity-50 leading-6 pt-0.5"
        style={{ minHeight: "1.5rem" }}
      />

      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className="shrink-0 border border-gray-600 bg-black text-white text-sm px-3 py-1 rounded transition-colors hover:border-green-600 hover:text-green-400 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Send
      </button>
    </div>
  );
}
