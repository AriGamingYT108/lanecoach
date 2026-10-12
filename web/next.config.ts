import type { NextConfig } from "next";
const config: NextConfig = {
  async rewrites() {
    return [{source: "/api/:path*", destination: `${process.env.API_ORIGIN || "http://127.0.0.1:8000"}/api/:path*`}];
  },
  async headers() {
    return [{source: "/:path*", headers: [
      {key: "X-Content-Type-Options", value: "nosniff"},
      {key: "Referrer-Policy", value: "no-referrer"},
      {key: "X-Frame-Options", value: "DENY"}
    ]}];
  }
};
export default config;
