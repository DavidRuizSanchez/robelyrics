import Link from "next/link";
import LogoBomba from "@/components/LogoBomba";
import InstagramLink from "@/components/InstagramLink";
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
    <header className="sticky top-0 z-40 relative flex items-center justify-between px-5 md:px-14 py-4 md:py-5 border-b border-divider bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/70">
      <Link
        href="/"
        data-cursor="hover"
        className="flex items-center gap-3"
        aria-label="Entre Interiores · inicio"
      >
        <LogoBomba size={40} />
        <span className="font-serif text-lg md:text-xl text-ink leading-none tracking-tight">
          Entre Interiores
        </span>
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
        <Link
          href="/discografia"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
        >
          Discografía
        </Link>
        <Link
          href="/blog"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
          title="De manera urgente · noticias y memoria"
        >
          De manera urgente
        </Link>
        <Link
          href="/buscar"
          data-cursor="hover"
          className="text-ink-dim hover:text-ink transition-colors"
        >
          Buscar
        </Link>
        <InstagramLink size={18} className="text-ink-dim hover:text-accent transition-colors" />
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

      {/* Menú móvil: hamburguesa CSS pura (<details>), sin JS. Enlaces <a>
          reales y rastreables. Solo visible por debajo de `md`. */}
      <details className="md:hidden group [&_summary::-webkit-details-marker]:hidden">
        <summary
          className="list-none cursor-pointer p-2 -mr-2 text-ink"
          aria-label="Abrir menú"
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <line x1="3" y1="6" x2="21" y2="6" className="group-open:hidden" />
            <line x1="3" y1="12" x2="21" y2="12" className="group-open:hidden" />
            <line x1="3" y1="18" x2="21" y2="18" className="group-open:hidden" />
            <line x1="5" y1="5" x2="19" y2="19" className="hidden group-open:block" />
            <line x1="19" y1="5" x2="5" y2="19" className="hidden group-open:block" />
          </svg>
        </summary>
        <nav className="absolute top-full left-0 right-0 bg-bg border-b border-divider px-5 py-5 flex flex-col gap-5 font-mono text-[11px] tracking-[2.5px] uppercase">
          <Link href="/extremoduro" className="text-ink-dim hover:text-ink transition-colors">Extremoduro</Link>
          <Link href="/robe" className="text-ink-dim hover:text-ink transition-colors">Robe</Link>
          <Link href="/discografia" className="text-ink-dim hover:text-ink transition-colors">Discografía</Link>
          <Link href="/blog" className="text-ink-dim hover:text-ink transition-colors" title="De manera urgente · noticias y memoria">De manera urgente</Link>
          <Link href="/buscar" className="text-ink-dim hover:text-ink transition-colors">Buscar</Link>
          {me ? (
            <>
              <Link href="/biblioteca" className="text-ink-dim hover:text-ink transition-colors">Biblioteca</Link>
              {me.is_admin && (
                <Link href="/biblioteca/admin/sources" className="text-ink-dim hover:text-ink transition-colors">Admin</Link>
              )}
              <form action="/logout" method="post">
                <button type="submit" className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]">salir</button>
              </form>
            </>
          ) : (
            <Link href="/login" className="text-accent hover:text-ink transition-colors">acceder</Link>
          )}
          <InstagramLink showHandle className="text-ink-dim hover:text-accent transition-colors pt-2 border-t border-divider/60" />
        </nav>
      </details>
    </header>
  );
}
