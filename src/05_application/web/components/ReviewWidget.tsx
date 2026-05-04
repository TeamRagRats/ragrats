"use client";

import { useState } from "react";
import { submitReview } from "@/lib/api";

type State = "idle" | "explaining" | "submitted";

interface ReviewWidgetProps {
  queryId: string;
}

export default function ReviewWidget({ queryId }: ReviewWidgetProps) {
  const [state, setState] = useState<State>("idle");
  const [feedback, setFeedback] = useState("");

  async function handleYes() {
    setState("submitted");
    try {
      await submitReview(queryId, true, null);
    } catch {
      // fire-and-forget — don't surface review errors to user
    }
  }

  function handleNo() {
    setState("explaining");
  }

  async function handleSubmit() {
    setState("submitted");
    try {
      await submitReview(queryId, false, feedback || null);
    } catch {
      // fire-and-forget
    }
  }

  if (state === "submitted") {
    return (
      <p className="text-gray-500 text-xs">Thanks ✓</p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <span className="text-gray-500 text-xs">Did we provide you with the correct answer?</span>
        {state === "idle" && (
          <>
            <button
              onClick={handleYes}
              className="border border-gray-600 bg-black text-white text-xs px-2 py-0.5 hover:border-green-600 hover:text-green-400"
            >
              Yes
            </button>
            <button
              onClick={handleNo}
              className="border border-gray-600 bg-black text-white text-xs px-2 py-0.5 hover:border-green-600 hover:text-green-400"
            >
              No
            </button>
          </>
        )}
      </div>
      {state === "explaining" && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Correct answer?"
            className="bg-black border border-gray-600 text-white text-xs px-2 py-0.5 placeholder-gray-700 focus:outline-none focus:border-gray-400 w-64"
          />
          <button
            onClick={handleSubmit}
            className="border border-gray-600 bg-black text-white text-xs px-2 py-0.5 hover:border-green-600 hover:text-green-400"
          >
            Submit
          </button>
        </div>
      )}
    </div>
  );
}
