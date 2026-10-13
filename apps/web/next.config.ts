import path from "node:path";
import type { NextConfig } from "next";

const buildCpus = Number(process.env.NEXT_BUILD_CPUS);

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, "../.."),
  transpilePackages: ["@agrayian/sdk", "@agrayian/ui", "@agrayian/types"],
  eslint: {
    ignoreDuringBuilds: process.env.NEXT_DISABLE_ESLINT === "1",
  },
  typescript: {
    ignoreBuildErrors: process.env.SKIP_NEXT_TYPECHECK === "1",
  },
};

if (Number.isFinite(buildCpus) && buildCpus > 0) {
  nextConfig.experimental = { cpus: buildCpus };
}

export default nextConfig;
