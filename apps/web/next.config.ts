import type { NextConfig } from "next";

/**
 * The public NileTech website (spec 002).
 *
 * Server-rendered rather than statically generated, deliberately. The site's
 * content comes from the seeded dataset, and a reseed must be visible
 * immediately — a build-time snapshot would leave the site describing the
 * previous dataset with nothing to notice the drift (research R1).
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,

  // `@eaios/ui` ships TypeScript sources rather than a build, so Next compiles
  // it alongside the app.
  transpilePackages: ["@eaios/ui", "@eaios/contracts"],

  // Traced output so the container ships the server and its dependencies
  // without the whole workspace.
  output: "standalone",
  outputFileTracingRoot: new URL("../../", import.meta.url).pathname,

  // The API base differs between the browser (localhost via the published
  // port) and the server component (the Compose service name), so both are
  // read from the environment rather than hard-coded.
  env: {
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  },

  eslint: {
    // Linting runs once for the whole workspace via the root `pnpm lint`.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
