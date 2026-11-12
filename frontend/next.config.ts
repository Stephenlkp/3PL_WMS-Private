import type { NextConfig } from "next";
import { privateIpv4 } from "./src/lib/lan";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  allowedDevOrigins: privateIpv4(),
  devIndicators: false,
  async rewrites() {
    const api = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
