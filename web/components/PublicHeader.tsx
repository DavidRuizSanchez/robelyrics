import Link from "next/link";
import LogoBomba from "@/components/LogoBomba";
import InstagramLink from "@/components/InstagramLink";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";

// Submenú compartido por Extremoduro y Robe. "Historia" es lo único propio de
// cada artista; el resto (grupos amigos, colegas, sellos, libros) son URLs
// globales compartidas. Discografía va filtrada por artista.
function artistItems(slug: "extremoduro" | "robe") {
  return [
    { href: `/${slug}`, label: "Historia" },
    { href: `/discografia?artist=${slug}`, label: "Discografía" },
  ];
}

const linkCls = "text-ink-dim hover:text-ink transition-colors";

// Desktop: trigger pulsable (va a /artista) + desplegable por hover (CSS puro).
function ArtistDropdown({ slug, label }: { slug: "extremoduro" | "robe"; label: string }) {
  return (
    <div className="relative group/art">
      {/* El trigger solo despliega (no enlaza): el enlace a la página del
          artista es el item "Historia", para no duplicar el enlace. */}
      <span data-cursor="hover" className={`${linkCls} inline-flex items-center gap-1 cursor-default select-none`}>
        {label}
        <span aria-hidden className="text-[8px] opacity-70 group-hover/art:rotate-180 transition-transform">▼</span>
      </span>
      <div className="invisible opacity-0 group-hover/art:visible group-hover/art:opacity-100 transition-opacity absolute left-1/2 -translate-x-1/2 top-full pt-3 z-50">
        <div className="bg-bg border border-divider rounded-sm py-2 min-w-[210px] flex flex-col shadow-lg">
          {artistItems(slug).map((it) => (
            <Link
              key={it.label}
              href={it.href}
              data-cursor="hover"
              className="px-5 py-2 text-ink-dim hover:text-accent hover:bg-divider/20 transition-colors normal-case tracking-[1px]"
            >
              {it.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

// Mobile: acordeón con <details> anidado dentro del menú principal.
function ArtistAccordion({ slug, label }: { slug: "extremoduro" | "robe"; label: string }) {
  return (
    <details className="group/m">
      <summary className="list-none cursor-pointer flex items-center justify-between text-ink-dim hover:text-ink [&::-webkit-details-marker]:hidden">
        {label}
        <span aria-hidden className="text-[8px] group-open/m:rotate-180 transition-transform">▼</span>
      </summary>
      <div className="flex flex-col gap-3 pl-4 pt-3 border-l border-divider/60 mt-2">
        {artistItems(slug).map((it) => (
          <Link key={it.label} href={it.href} className="text-ink-dim hover:text-accent transition-colors normal-case tracking-[1px]">
            {it.label}
          </Link>
        ))}
      </div>
    </details>
  );
}

const SearchIcon = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.5" y2="16.5" />
  </svg>
);

export default async function PublicHeader() {
  let me: AuthMe | null = null;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    me = null;
  }

  return (
    <header className="sticky top-0 z-40 relative flex items-center justify-between px-5 md:px-14 py-4 md:py-5 border-b border-divider bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/70">
      <Link href={me ? "/biblioteca" : "/"} data-cursor="hover" className="flex items-center gap-3" aria-label="Entre Interiores · inicio">
        <LogoBomba size={40} />
        <span className="font-serif text-lg md:text-xl text-ink leading-none tracking-tight">Entre Interiores</span>
      </Link>

      {/* === DESKTOP === */}
      <nav className="hidden lg:flex items-center gap-6 font-mono text-[10px] tracking-[2.5px] uppercase">
        <ArtistDropdown slug="extremoduro" label="Extremoduro" />
        <ArtistDropdown slug="robe" label="Robe" />
        <Link href="/blog" data-cursor="hover" className={linkCls} title="De manera urgente · noticias y memoria">De manera urgente</Link>
        <Link href="/biblioteca/consultorio" data-cursor="hover" className="text-accent hover:text-ink transition-colors" title="Pregúntame lo que quieras, que pa' eso sigo en el aire">Pregúntale al viento</Link>
        <Link href="/biblioteca?mode=semantic#search" data-cursor="hover" className="text-accent hover:text-ink transition-colors" title="Dime qué sientes y te busco el verso que lo dice">Como lo diría Robe</Link>
        <Link href="/buscar" data-cursor="hover" className={linkCls} aria-label="Buscar" title="Buscar">{SearchIcon}</Link>
        {!me && (
          <Link href="/blog#suscribete" data-cursor="hover" className="border border-accent/60 text-accent hover:bg-accent hover:text-white px-3 py-1.5 transition-colors" title="Suscríbete al diario">Suscríbete</Link>
        )}
        <Link href="/biblioteca/donar" data-cursor="hover" className={linkCls} title="Echar una mano para que esto siga vivo">Apoyar</Link>
        <InstagramLink size={18} className="text-ink-dim hover:text-accent transition-colors" />
        {me ? (
          <>
            {me.is_admin && <Link href="/biblioteca/admin/sources" data-cursor="hover" className={linkCls}>Admin</Link>}
            <form action="/logout" method="post" className="inline">
              <button type="submit" data-cursor="hover" className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]">salir</button>
            </form>
          </>
        ) : (
          <Link href="/login" data-cursor="hover" className="border border-accent/60 text-accent hover:bg-accent hover:text-white px-4 py-2 transition-colors">acceder</Link>
        )}
      </nav>

      {/* === MOBILE === (mismas opciones que desktop, adaptadas a acordeón) */}
      <details className="lg:hidden group [&_summary::-webkit-details-marker]:hidden">
        <summary className="list-none cursor-pointer p-2 -mr-2 text-ink" aria-label="Abrir menú">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <line x1="3" y1="6" x2="21" y2="6" className="group-open:hidden" />
            <line x1="3" y1="12" x2="21" y2="12" className="group-open:hidden" />
            <line x1="3" y1="18" x2="21" y2="18" className="group-open:hidden" />
            <line x1="5" y1="5" x2="19" y2="19" className="hidden group-open:block" />
            <line x1="19" y1="5" x2="5" y2="19" className="hidden group-open:block" />
          </svg>
        </summary>
        <nav className="absolute top-full left-0 right-0 bg-bg border-b border-divider px-5 py-5 flex flex-col gap-5 font-mono text-[11px] tracking-[2.5px] uppercase max-h-[80vh] overflow-y-auto">
          <ArtistAccordion slug="extremoduro" label="Extremoduro" />
          <ArtistAccordion slug="robe" label="Robe" />
          <Link href="/blog" className={linkCls} title="De manera urgente · noticias y memoria">De manera urgente</Link>
          <Link href="/biblioteca/consultorio" className="text-accent hover:text-ink transition-colors">Pregúntale al viento</Link>
          <Link href="/biblioteca?mode=semantic#search" className="text-accent hover:text-ink transition-colors">Como lo diría Robe</Link>
          <Link href="/buscar" className={linkCls}>Buscar</Link>
          {!me && (
            <Link href="/blog#suscribete" className="text-accent hover:text-ink transition-colors">Suscríbete al diario</Link>
          )}
          <Link href="/biblioteca/donar" className={linkCls}>Apoyar el proyecto</Link>
          {me ? (
            <>
              {me.is_admin && <Link href="/biblioteca/admin/sources" className={linkCls}>Admin</Link>}
              <form action="/logout" method="post"><button type="submit" className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]">salir</button></form>
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
