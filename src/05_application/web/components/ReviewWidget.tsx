"use client";

import { useState } from "react";
import { submitReview } from "@/lib/api";

interface ReviewWidgetProps {
  queryId: string;
}

export default function ReviewWidget({ queryId }: ReviewWidgetProps) {
  const [submitted, setSubmitted] = useState(false);

  async function handleReview(isCorrect: boolean) {
    setSubmitted(true);
    try {
      await submitReview(queryId, isCorrect, null);
    } catch (err) {
      console.error("Review submission failed:", err);
    }
  }

  if (submitted) {
    return <p className="text-gray-500 text-sm">Thanks ✓</p>;
  }

  return (
    <div className="flex items-center gap-3">
      <span className="text-gray-500 text-sm">Did we provide you with the correct answer?</span>
      <button
        onClick={() => handleReview(true)}
        className="border border-gray-600 bg-black text-white text-sm px-2 py-0.5 hover:border-green-600 hover:text-green-400"
      >
        Yes
      </button>
      <button
        onClick={() => handleReview(false)}
        className="border border-gray-600 bg-black text-white text-sm px-2 py-0.5 hover:border-green-600 hover:text-green-400"
      >
        No
      </button>
    </div>
  );
}
