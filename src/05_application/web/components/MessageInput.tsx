"use client";

import { useEffect, useRef, useState } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

const DRAFT_KEY = "chat:draft";

export default function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const saved = sessionStorage.getItem(DRAFT_KEY);
    if (saved) setValue(saved);
  }, []);

  useEffect(() => {
    if (value) sessionStorage.setItem(DRAFT_KEY, value);
    else sessionStorage.removeItem(DRAFT_KEY);
  }, [value]);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    sessionStorage.removeItem(DRAFT_KEY);
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
    <div className="w-[65%] mx-auto flex items-start gap-3 px-6 py-4 my-4 bg-black border border-white">
      <span className="shrink-0 text-gray-400 text-base pt-1 select-none">Question:</span>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder="Ask operational questions regarding the 20 voyages here."
        className="flex-1 bg-transparent text-white text-base placeholder-gray-400 caret-white resize-none overflow-hidden focus:outline-none disabled:opacity-50 leading-6 pt-0.5"
        style={{ minHeight: "1.5rem" }}
      />

      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className="shrink-0 border border-gray-600 bg-black text-white text-base px-3 py-1 transition-colors hover:border-green-600 hover:text-green-400 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Send
      </button>
    </div>
  );
}
