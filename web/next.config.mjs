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
};

export default nextConfig;
