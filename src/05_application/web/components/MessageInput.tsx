"use client";

import { useState, useRef } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="bg-black px-6 py-4 flex items-center gap-4 w-full max-w-xl">
      <div
        className="flex-1 flex items-center cursor-text relative"
        onClick={() => inputRef.current?.focus()}
      >
        <span className="text-white text-sm select-none">Question:&nbsp;</span>
        <span className="text-white text-sm whitespace-pre">{value}</span>
        <span className={`text-white text-sm${focused ? " animate-blink" : " opacity-0"}`}>|</span>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          disabled={disabled}
          className="absolute opacity-0 w-0 h-0 pointer-events-none"
          aria-label="Question input"
        />
      </div>

      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className="bg-gray-700 text-white text-sm px-4 py-2 rounded hover:bg-gray-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Send
      </button>
    </div>
  );
}
