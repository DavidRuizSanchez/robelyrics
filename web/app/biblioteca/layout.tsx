import Link from "next/link";
import Header from "@/components/Header";
import YoutubeFloatingPlayer from "@/components/YoutubeFloatingPlayer";
import { apiFetch } from "@/lib/api";
import { YoutubePlayerProvider } from "@/lib/youtube-player-context";
import type { AuthMe } from "@/lib/types";

// Layout de la capa privada (auth obligatoria por middleware).
// El middleware garantiza token, así que /auth/me debería responder. Si falla
// (sesión caducada en el momento exacto), tratamos como no admin y seguimos.
//
// Esta capa NO debe indexarse: añadimos la metadata robots correspondiente.

export const metadata = {
  robots: { index: false, follow: false },
};

export default async function BibliotecaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let isAdmin = false;
  try {
    const me = await apiFetch<AuthMe>("/auth/me");
    isAdmin = me.is_admin;
  } catch {
    isAdmin = false;
  }

  return (
    <YoutubePlayerProvider>
      <Header isAdmin={isAdmin} />
      {children}
      <YoutubeFloatingPlayer />
      <BibliotecaFooter />
    </YoutubePlayerProvider>
  );
}

function BibliotecaFooter() {
  return (
    <footer className="px-5 md:px-14 py-8 mt-16 border-t border-divider max-w-[1100px] mx-auto">
      <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint text-center leading-relaxed">
        contenido fan derivado disponible bajo{" "}
        <Link
          href="https://creativecommons.org/licenses/by-nc-sa/3.0/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent hover:underline"
        >
          CC-BY-NC-SA 3.0
        </Link>{" "}
        ·{" "}
        <Link
          href="/biblioteca/atribuciones"
          data-cursor="hover"
          className="text-accent hover:underline"
        >
          atribuciones
        </Link>
      </p>
    </footer>
  );
}
