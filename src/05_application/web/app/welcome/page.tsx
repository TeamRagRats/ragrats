"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function WelcomePage() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    async function check() {
      try {
        const res = await fetch("/api/health", { credentials: "include" });
        if (res.status === 401) {
          router.replace("/login");
          return;
        }
        setAuthChecked(true);
      } catch {
        router.replace("/login");
      }
    }
    check();
  }, [router]);

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <p className="text-white text-base">Loading…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-black px-8 py-12">
      <div className="w-full max-w-3xl flex flex-col gap-10">
        <h1 className="text-6xl font-bold text-white tracking-tight">Welcome</h1>

        <div className="flex flex-col gap-6 text-2xl text-white leading-relaxed">
          <p>
            The system has read all <span className="font-bold">Remark</span> and{" "}
            <span className="font-bold">Softmar</span> data from{" "}
            <span className="font-bold">20 voyages</span>.
          </p>
          <p>
            You can ask it questions like:{" "}
            <em className="text-green-400">
              &ldquo;Have we had any cargo damage in Brazil?&rdquo;
            </em>
          </p>
          <p>Your task: ask questions and rate the answers.</p>
        </div>

        <div className="flex justify-end pt-6">
          <button
            onClick={() => router.push("/chat")}
            className="border-2 border-gray-600 bg-black text-white text-2xl px-12 py-4 transition-colors hover:border-green-600 hover:text-green-400"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
