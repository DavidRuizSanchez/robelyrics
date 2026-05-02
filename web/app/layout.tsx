import type { Metadata } from "next";
import { Caveat, Cormorant_Garamond, JetBrains_Mono } from "next/font/google";
import { cookies } from "next/headers";
import Header from "@/components/Header";
import InkCursor from "@/components/InkCursor";
import YoutubeFloatingPlayer from "@/components/YoutubeFloatingPlayer";
import { YoutubePlayerProvider } from "@/lib/youtube-player-context";
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
  title: "Entre Interiores · RobeLyrics",
  description:
    "El universo de Robe Iniesta y Extremoduro, verso a verso. Buscador semántico personal.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const isAuthed = Boolean((await cookies()).get("robelyrics_token")?.value);
  const fontVars = `${cormorant.variable} ${jetbrains.variable} ${caveat.variable}`;

  return (
    <html lang="es" className={`dark ${fontVars}`} suppressHydrationWarning>
      <body
        className="bg-bg-deep text-ink antialiased min-h-screen font-serif"
        suppressHydrationWarning
      >
        <YoutubePlayerProvider>
          <InkCursor />
          {isAuthed && <Header />}
          {children}
          <YoutubeFloatingPlayer />
        </YoutubePlayerProvider>
      </body>
    </html>
  );
}
