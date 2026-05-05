import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  allowedDevOrigins: ["neglector-willing-crier.ngrok-free.dev"],
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8001/:path*" },
    ];
  },
};

export default nextConfig;
