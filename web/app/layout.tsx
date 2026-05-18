import type { Metadata } from "next";
import { Caveat, JetBrains_Mono, Spectral } from "next/font/google";
import ConsentManager from "@/components/ConsentManager";
import InkCursor from "@/components/InkCursor";
import { safeJsonLd } from "@/lib/safe-json-ld";
import "./globals.css";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

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

  // Schema en @graph: el WebSite del proyecto referencia al Person canónico
  // del autor (definido en davidruizsanchez.es/#person). No duplicamos sus
  // datos, los enlazamos por @id — Google sigue la referencia y consolida
  // señal de E-E-A-T.
  const siteGraph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: "Entre Interiores",
        alternateName: "Cancionero de Robe y Extremoduro",
        description:
          "Disco a disco, canción a canción: el universo de Robe y Extremoduro contado por sus letras y por la comunidad de fans.",
        inLanguage: "es-ES",
        creator: { "@id": "https://davidruizsanchez.es/#person" },
        publisher: { "@id": "https://davidruizsanchez.es/#person" },
        potentialAction: {
          "@type": "SearchAction",
          target: {
            "@type": "EntryPoint",
            urlTemplate: `${SITE_URL}/buscar?q={search_term_string}`,
          },
          "query-input": "required name=search_term_string",
        },
      },
      {
        "@type": "Person",
        "@id": "https://davidruizsanchez.es/#person",
        name: "David Ruiz Sánchez",
        givenName: "David",
        familyName: "Ruiz Sánchez",
        url: "https://davidruizsanchez.es",
        jobTitle: "Partner & Head of SEO",
        worksFor: {
          "@type": "Organization",
          name: "Convertix",
          url: "https://convertix.net",
        },
        sameAs: [
          "https://www.linkedin.com/in/davidruizsanchez/",
          "https://github.com/DavidRuizSanchez",
          "https://x.com/davidruiz_s",
        ],
      },
    ],
  };

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
