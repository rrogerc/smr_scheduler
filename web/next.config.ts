import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  // Base path might be needed if hosted on a subpath (e.g. /smr_scheduler)
  // We will assume root or let GitHub Action handle it, but usually for user pages it's /repo-name
  basePath: '/smr_scheduler', 
};

export default nextConfig;
