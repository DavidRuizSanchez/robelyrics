import Link from "next/link";
import { LogoSunCloud } from "@/components/Logo";
import { T } from "@/lib/theme";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";

export default async function PublicHeader() {
  // Detectar sesión opcionalmente: la mayoría de visitantes son anónimos,
  // por lo que un fallo (sin cookie / token inválido) cae a estado público.
  let me: AuthMe | null = null;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    me = null;
  }

  return (
    <header className="sticky top-0 z-40 flex items-center justify-between px-5 md:px-14 py-4 md:py-5 border-b border-divider bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/70">
      <Link href="/" data-cursor="hover" className="block">
        <LogoSunCloud name="Entre Interiores" color={T.ink} scale={0.7} />
      </Link>

      <nav className="hidden md:flex items-center gap-7 font-mono text-[10px] tracking-[2.5px] uppercase">
        <Link
          href="/extremoduro"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
        >
          Extremoduro
        </Link>
        <Link
          href="/robe"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
        >
          Robe
        </Link>
        {me ? (
          <>
            <Link
              href="/biblioteca"
              data-cursor="hover"
              className="text-ink-dim hover:text-ink transition-colors"
            >
              Biblioteca
            </Link>
            {me.is_admin && (
              <Link
                href="/biblioteca/admin/sources"
                data-cursor="hover"
                className="text-ink-dim hover:text-ink transition-colors"
              >
                Admin
              </Link>
            )}
            <form action="/logout" method="post" className="inline">
              <button
                type="submit"
                data-cursor="hover"
                className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]"
              >
                salir
              </button>
            </form>
          </>
        ) : (
          <Link
            href="/login"
            data-cursor="hover"
            className="border border-accent/60 text-accent hover:bg-accent hover:text-white px-4 py-2 transition-colors"
          >
            acceder
          </Link>
        )}
      </nav>
    </header>
  );
}
