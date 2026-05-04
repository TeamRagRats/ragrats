"use client";

import { useState, useRef } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

const btnClass =
  "shrink-0 border border-gray-600 bg-black text-white text-sm px-3 py-1 rounded transition-colors hover:border-green-600 hover:text-green-400 disabled:opacity-40 disabled:cursor-not-allowed";

export default function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="bg-black px-6 py-3 flex items-start gap-4 w-full max-w-xl">
      {/* "Question:" — fixed top-left */}
      <span className="shrink-0 text-white text-sm pt-0.5 select-none">Question:</span>

      {/* Growing text area with blinking cursor overlay */}
      <div
        className="flex-1 relative cursor-text min-h-5"
        onClick={() => textareaRef.current?.focus()}
      >
        {/* Mirror div drives the height */}
        <div className="text-white text-sm whitespace-pre-wrap break-words invisible" aria-hidden>
          {value || " "}
        </div>

        {/* Visible cursor + text overlay */}
        <div className="absolute inset-0 text-white text-sm whitespace-pre-wrap break-words pointer-events-none">
          {value}
          <span className={focused ? "animate-blink" : "opacity-0"}>|</span>
        </div>

        {/* Hidden textarea captures input */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          disabled={disabled}
          rows={1}
          className="absolute inset-0 w-full h-full opacity-0 resize-none cursor-text"
          aria-label="Question input"
        />
      </div>

      {/* Send — fixed top-right */}
      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className={btnClass}
      >
        Send
      </button>
    </div>
  );
}
