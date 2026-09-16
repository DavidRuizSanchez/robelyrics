import type { Metadata } from "next";
import { Caveat, JetBrains_Mono, Spectral } from "next/font/google";
import ConsentManager from "@/components/ConsentManager";
import GlobalErrata from "@/components/GlobalErrata";
import InkCursor from "@/components/InkCursor";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { buildGraph, siteGraphNodes } from "@/lib/schema-graph";
import { SITE_URL } from "@/lib/site";
import "./globals.css";

const spectral = Spectral({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-mono",
  display: "swap",
});

const caveat = Caveat({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-hand",
  display: "swap",
});

export const metadata: Metadata = {
  // Sin esto Next resuelve las imágenes relativas (las carátulas de
  // /album-covers) contra http://localhost:3000, y así salían og:image y
  // twitter:image en las fichas de disco y canción.
  metadataBase: new URL(SITE_URL),
  title: "Entre Interiores · Cancionero de Robe y Extremoduro",
  description:
    "Disco a disco, canción a canción: el universo de Robe y Extremoduro contado por sus letras y por la comunidad de fans.",
};

// NO se marca `force-dynamic` aquí. Estuvo de mayo a septiembre de 2026 y
// anulaba el `revalidate` de todas las páginas públicas: cada petición
// re-renderizaba entera y Googlebot medía 571 ms de media en GSC. Lo dinámico
// (la sesión) vive en /biblioteca, que lo declara en su propio layout, y en
// `ForSession`, que la pide desde el cliente.

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const fontVars = `${spectral.variable} ${jetbrains.variable} ${caveat.variable}`;

  // GA4 se carga solo si hay ID definido en env Y el usuario ha dado
  // consentimiento explícito en el banner (RGPD/ePrivacy). Si no hay ID,
  // ni se monta el manager, así dev no muestra banner inútil.
  const gaId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

  // Grafo global del sitio (una sola vez): WebSite + Organization (publisher)
  // + Person autor (referenciado por @id, no duplicado). Las páginas emiten su
  // propio @graph y referencian estos nodos por @id. Ver web/lib/schema-graph.ts.
  const siteGraph = buildGraph(siteGraphNodes());

  return (
    <html lang="es" className={`dark ${fontVars}`} suppressHydrationWarning>
      <body
        className="bg-bg-deep text-ink antialiased min-h-screen font-serif"
        suppressHydrationWarning
      >
        <InkCursor />
        {children}
        <GlobalErrata />
        {gaId && <ConsentManager gaId={gaId} />}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(siteGraph) }}
        />
      </body>
    </html>
  );
}
