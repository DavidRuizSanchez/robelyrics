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
    <footer className="px-5 md:px-14 py-10 mt-16 border-t border-divider max-w-[1100px] mx-auto space-y-5">
      <div className="flex flex-col md:flex-row gap-3 md:gap-4 items-center justify-center">
        <Link
          href="https://www.patreon.com/c/EntreInteriores"
          target="_blank"
          rel="noopener noreferrer"
          data-cursor="hover"
          className="border border-accent text-accent hover:bg-accent hover:text-white font-mono text-[10px] tracking-[3px] uppercase px-5 py-2.5 transition-colors"
        >
          apoyar en Patreon
        </Link>
        <Link
          href="https://ko-fi.com/entreinteriores"
          target="_blank"
          rel="noopener noreferrer"
          data-cursor="hover"
          className="border border-divider text-ink-dim hover:border-accent hover:text-accent font-mono text-[10px] tracking-[3px] uppercase px-5 py-2.5 transition-colors"
        >
          invitar a un café · Ko-fi
        </Link>
      </div>
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
        </Link>{" "}
        ·{" "}
        <Link
          href="/biblioteca/donar"
          data-cursor="hover"
          className="text-accent hover:underline"
        >
          donar
        </Link>
      </p>
    </footer>
  );
}
