import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  allowedDevOrigins: ["weco-proto-type.ngrok.io", "weco-proto-api.ngrok.io"],
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8001/:path*" },
    ];
  },
};

export default nextConfig;
