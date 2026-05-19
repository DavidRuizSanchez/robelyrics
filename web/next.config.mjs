/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Hot-reload con bind mount en docker requiere polling
  webpack: (config, { dev }) => {
    if (dev) {
      config.watchOptions = {
        poll: 1000,
        aggregateTimeout: 300,
      };
    }
    return config;
  },
  // Marca como noindex las requests de prefetch RSC. Aplicamos por dos vías
  // (query param ?_rsc= y cabecera RSC: 1) porque Googlebot/otros bots pueden
  // disparar la request por cualquiera de las dos formas.
  async headers() {
    return [
      {
        source: "/:path*",
        has: [{ type: "query", key: "_rsc" }],
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
        ],
      },
      {
        source: "/:path*",
        has: [{ type: "header", key: "rsc", value: "1" }],
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
        ],
      },
    ];
  },
};

export default nextConfig;
