import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RobeLyrics",
  description: "Buscador semántico del universo Extremoduro / Robe Iniesta",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" className="dark">
      <body className="bg-zinc-950 text-zinc-100 antialiased">{children}</body>
    </html>
  );
}
