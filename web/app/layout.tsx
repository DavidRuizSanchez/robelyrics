import type { Metadata } from "next";
import { Merriweather } from "next/font/google";
import { cookies } from "next/headers";
import Header from "@/components/Header";
import YoutubeFloatingPlayer from "@/components/YoutubeFloatingPlayer";
import { YoutubePlayerProvider } from "@/lib/youtube-player-context";
import "./globals.css";

const merriweather = Merriweather({
  subsets: ["latin"],
  weight: ["400", "700", "900"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "RobeLyrics",
  description: "Buscador semántico del universo Extremoduro / Robe Iniesta",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Mostramos el header solo si está autenticado (la cookie existe).
  const isAuthed = Boolean((await cookies()).get("robelyrics_token")?.value);

  return (
    <html lang="es" className={`dark ${merriweather.variable}`} suppressHydrationWarning>
      {/* suppressHydrationWarning: extensiones de navegador (ColorZilla, Grammarly,
          Honey, etc.) inyectan atributos en <body> tras el render del servidor.
          Sin esto, dev mode lanza un overlay de hydration en cada carga. */}
      <body
        className="bg-zinc-950 text-zinc-100 antialiased min-h-screen"
        suppressHydrationWarning
      >
        <YoutubePlayerProvider>
          {isAuthed && <Header />}
          {children}
          <YoutubeFloatingPlayer />
        </YoutubePlayerProvider>
      </body>
    </html>
  );
}
