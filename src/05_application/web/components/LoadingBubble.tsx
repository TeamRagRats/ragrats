"use client";

import { useEffect, useState } from "react";

export default function LoadingBubble() {
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    const interval = setInterval(() => {
      setDotCount((prev) => (prev % 3) + 1);
    }, 400);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex justify-start">
      <p className="text-blue-400 text-sm">{".".repeat(dotCount)}</p>
    </div>
  );
}
