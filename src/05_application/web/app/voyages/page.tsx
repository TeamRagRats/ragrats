"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getVoyages, type Voyage } from "@/lib/api";

export default function VoyagesPage() {
  const router = useRouter();
  const [voyages, setVoyages] = useState<Voyage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVoyages()
      .then(setVoyages)
      .catch((e) => {
        if (e.message?.includes("401")) {
          router.replace("/login");
        } else {
          setError(e.message ?? "Unknown error");
        }
      })
      .finally(() => setLoading(false));
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <p className="text-white text-base">Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <p className="text-red-400 text-base">{error}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-black px-8 py-12">
      <div className="w-full max-w-5xl flex flex-col gap-8">
        <h1 className="text-5xl font-bold text-white tracking-tight">Voyages in dataset</h1>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="py-3 pr-8 text-sm font-semibold text-gray-400 uppercase tracking-wider">Vessel</th>
                <th className="py-3 pr-8 text-sm font-semibold text-gray-400 uppercase tracking-wider">Cargo</th>
                <th className="py-3 pr-8 text-sm font-semibold text-gray-400 uppercase tracking-wider">Load</th>
                <th className="py-3 text-sm font-semibold text-gray-400 uppercase tracking-wider">Discharge</th>
              </tr>
            </thead>
            <tbody>
              {voyages.map((v, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-900 transition-colors">
                  <td className="py-4 pr-8 text-white text-base font-medium">{v.vessel_name ?? "—"}</td>
                  <td className="py-4 pr-8 text-gray-300 text-base">{v.commodity ?? "—"}</td>
                  <td className="py-4 pr-8 text-gray-300 text-base">{v.load_port ?? v.from_range ?? "—"}</td>
                  <td className="py-4 text-gray-300 text-base">{v.discharge_port ?? v.to_range ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex justify-end pt-4">
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
