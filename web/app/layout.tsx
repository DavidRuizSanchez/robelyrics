import type { Metadata } from "next";
import { Caveat, Cormorant_Garamond, JetBrains_Mono } from "next/font/google";
import ConsentManager from "@/components/ConsentManager";
import InkCursor from "@/components/InkCursor";
import "./globals.css";

const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
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
  title: "Entre Interiores · Cancionero de Robe Iniesta y Extremoduro",
  description:
    "Disco a disco, canción a canción: el universo de Robe Iniesta y Extremoduro contado por sus letras y por la comunidad de fans.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const fontVars = `${cormorant.variable} ${jetbrains.variable} ${caveat.variable}`;

  // GA4 se carga solo si hay ID definido en env Y el usuario ha dado
  // consentimiento explícito en el banner (RGPD/ePrivacy). Si no hay ID,
  // ni se monta el manager, así dev no muestra banner inútil.
  const gaId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

  return (
    <html lang="es" className={`dark ${fontVars}`} suppressHydrationWarning>
      <body
        className="bg-bg-deep text-ink antialiased min-h-screen font-serif"
        suppressHydrationWarning
      >
        <InkCursor />
        {children}
        {gaId && <ConsentManager gaId={gaId} />}
      </body>
    </html>
  );
}
