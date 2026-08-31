import type { NextConfig } from "next";

// The engine is a standard-library Python server (`make web-api`). Proxying to
// it here means the browser only ever talks to one origin, so there is no CORS
// story and no API base URL to configure per environment.
const ENGINE = process.env.LEDGERGATE_API ?? "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${ENGINE}/api/:path*` }];
  },
};

export default nextConfig;
