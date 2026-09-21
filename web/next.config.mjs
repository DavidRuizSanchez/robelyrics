/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Servimos imágenes remotas (Wikimedia Commons) optimizadas a WebP/AVIF
  // mediante /_next/image. Sólo whitelist de hosts confiables.
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      {
        protocol: "https",
        hostname: "upload.wikimedia.org",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "commons.wikimedia.org",
        pathname: "/**",
      },
      {
        // Arte IA de entidades abstractas (conceptos/temas) alojado en Cloudinary.
        protocol: "https",
        hostname: "res.cloudinary.com",
        pathname: "/**",
      },
    ],
    // Tiempo de cache en CDN — las imágenes de Commons no cambian
    minimumCacheTTL: 60 * 60 * 24 * 30, // 30 días
  },
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
  // Sellos discográficos migrados de /grupos/<slug> a /sellos/<slug>.
  // Redirect 308 permanente por si alguna URL antigua quedó indexada.
  async redirects() {
    const labelSlugs = [
      "el-dromedario-records",
      "dro",
      "avispa",
      "pasion",
      "warner",
      "muxikes",
      "la-gran-belleza-records",
    ];
    // Posts retirados que tenían un gemelo publicado: la URL vieja manda su
    // autoridad a la que se queda, en vez de dar 404. `statusCode: 301` y
    // `permanent` son excluyentes en Next; los sellos se quedan con `permanent`
    // (308) porque ya estaban así y cambiarlo no aporta nada.
    const postRedirects = [
      {
        source: "/blog/extremoduro-la-evolucion-del-rock-transgresivo-en-espana-2",
        destination: "/blog/extremoduro-la-evolucion-del-rock-transgresivo-en-espana",
      },
    ];
    return [
      ...labelSlugs.map((slug) => ({
        source: `/grupos/${slug}`,
        destination: `/sellos/${slug}`,
        permanent: true,
      })),
      ...postRedirects.map((r) => ({ ...r, statusCode: 301 })),
    ];
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
