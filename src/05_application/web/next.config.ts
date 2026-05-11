import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  allowedDevOrigins: ["weco-proto-type.ngrok.io", "weco-proto-api.ngrok.io", "192.168.0.115", "100.97.43.120"],
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${process.env.API_URL ?? "http://localhost:8001"}/:path*` },
    ];
  },
};

export default nextConfig;
