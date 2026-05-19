import type { MetadataRoute } from "next";

const SITE_URL = process.env.SITE_URL || "https://entreinteriores.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/"],
        disallow: ["/biblioteca/", "/login", "/logout", "/api/", "/*?_rsc="],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
