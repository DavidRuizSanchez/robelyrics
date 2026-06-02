import type { Metadata } from "next";
import { Caveat, JetBrains_Mono, Spectral } from "next/font/google";
import ConsentManager from "@/components/ConsentManager";
import InkCursor from "@/components/InkCursor";
import { safeJsonLd } from "@/lib/safe-json-ld";
import { buildGraph, siteGraphNodes } from "@/lib/schema-graph";
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
  title: "Entre Interiores · Cancionero de Robe y Extremoduro",
  description:
    "Disco a disco, canción a canción: el universo de Robe y Extremoduro contado por sus letras y por la comunidad de fans.",
};

// Todo el site se sirve dinámico: las páginas dependen de cookies (sesión) y
// de fetches al api en runtime. Marcarlo en el layout evita prerenderizar
// `/_not-found` y `/_error` que dispararían fallos por componentes cliente
// que se cargan globalmente (InkCursor, ConsentManager).
export const dynamic = "force-dynamic";

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
        {gaId && <ConsentManager gaId={gaId} />}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: safeJsonLd(siteGraph) }}
        />
      </body>
    </html>
  );
}
