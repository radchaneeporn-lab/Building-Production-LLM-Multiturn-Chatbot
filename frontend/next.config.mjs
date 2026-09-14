/** @type {import('next').NextConfig} */
const nextConfig = {
  // [LEARNING] "standalone" makes `next build` emit a self-contained
  // server (.next/standalone) with only the node_modules it actually
  // needs traced in — the Dockerfile below copies just that output
  // instead of the full node_modules tree into the final image layer.
  output: "standalone",
};

export default nextConfig;
