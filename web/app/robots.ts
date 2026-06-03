import type { MetadataRoute } from "next";

const SITE_URL = process.env.SITE_URL || "https://entreinteriores.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/"],
        disallow: [
          "/biblioteca/",
          "/login",
          "/logout",
          "/api/",
          "/*?_rsc=",
          // SERPs internas de búsqueda: thin content / duplicado del catálogo.
          // Bloqueamos las URLs con query (`/buscar?q=...`); el hub `/buscar`
          // sin query queda crawleable para la SearchAction de WebSite.
          "/buscar?",
        ],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
