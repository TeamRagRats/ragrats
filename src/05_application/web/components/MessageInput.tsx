"use client";

import { useState, useRef } from "react";

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
    // Reset textarea height
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
    // Auto-resize
    e.target.style.height = "auto";
    e.target.style.height = `${e.target.scrollHeight}px`;
  }

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className="flex items-end gap-2 border-t border-black bg-white px-4 py-3">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Ask something… (Enter to send, Shift+Enter for newline)"
        rows={1}
        disabled={disabled}
        className="flex-1 resize-none overflow-hidden border border-black rounded px-3 py-2 text-black bg-white placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-black disabled:opacity-50 max-h-40"
      />
      <button
        onClick={handleSend}
        disabled={!canSend}
        className="bg-black text-white text-sm font-semibold px-4 py-2 rounded hover:bg-gray-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
      >
        Send
      </button>
    </div>
  );
}
