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
      <div className="max-w-[75%] rounded-lg bg-black px-4 py-3 text-white text-sm min-w-[3rem]">
        {".".repeat(dotCount)}
      </div>
    </div>
  );
}
