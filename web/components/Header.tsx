import Link from "next/link";
import LogoBomba from "@/components/LogoBomba";

// Cabecera de la zona privada. Misma organización que la pública (paridad):
// desplegables Extremoduro/Robe + funcionalidades cross. Al estar logueado, las
// tools (Pregúntale al viento, Como lo diría Robe) van DIRECTAS, sin muro de
// registro. CSS puro (hover en desktop, <details> en móvil), sin JS.

function artistItems(slug: "extremoduro" | "robe") {
  return [
    { href: `/${slug}`, label: "Historia" },
    { href: `/discografia?artist=${slug}`, label: "Discografía" },
  ];
}

const linkCls = "text-ink-dim hover:text-ink transition-colors";

function ArtistDropdown({ slug, label }: { slug: "extremoduro" | "robe"; label: string }) {
  return (
    <div className="relative group/art">
      <Link href={`/${slug}`} data-cursor="hover" className={`${linkCls} inline-flex items-center gap-1`}>
        {label}
        <span aria-hidden className="text-[8px] opacity-70 group-hover/art:rotate-180 transition-transform">▼</span>
      </Link>
      <div className="invisible opacity-0 group-hover/art:visible group-hover/art:opacity-100 transition-opacity absolute left-1/2 -translate-x-1/2 top-full pt-3 z-50">
        <div className="bg-bg border border-divider rounded-sm py-2 min-w-[210px] flex flex-col shadow-lg">
          {artistItems(slug).map((it) => (
            <Link key={it.label} href={it.href} data-cursor="hover" className="px-5 py-2 text-ink-dim hover:text-accent hover:bg-divider/20 transition-colors normal-case tracking-[1px]">
              {it.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

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

export default function Header({ isAdmin = false }: { isAdmin?: boolean }) {
  return (
    <header className="sticky top-0 z-40 relative flex items-center justify-between px-5 md:px-14 py-4 md:py-6 border-b border-divider bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/70">
      <Link href="/biblioteca" data-cursor="hover" className="flex items-center gap-3" aria-label="Entre Interiores · inicio">
        <LogoBomba size={44} />
        <span className="font-serif text-lg md:text-xl text-ink leading-none tracking-tight">Entre Interiores</span>
      </Link>

      {/* === DESKTOP === */}
      <nav className="hidden lg:flex items-center gap-6 font-mono text-[10px] tracking-[2.5px] uppercase">
        <ArtistDropdown slug="extremoduro" label="Extremoduro" />
        <ArtistDropdown slug="robe" label="Robe" />
        <Link href="/blog" data-cursor="hover" className={linkCls}>De manera urgente</Link>
        <Link href="/biblioteca/consultorio" data-cursor="hover" className="text-accent hover:text-ink transition-colors">Pregúntale al viento</Link>
        <Link href="/biblioteca?mode=semantic#search" data-cursor="hover" className="text-accent hover:text-ink transition-colors">Como lo diría Robe</Link>
        <Link href="/biblioteca/donar" data-cursor="hover" className={linkCls}>Apoyar</Link>
        {isAdmin && <Link href="/biblioteca/admin/sources" data-cursor="hover" className={linkCls}>Admin</Link>}
        <form action="/logout" method="post" className="inline">
          <button type="submit" data-cursor="hover" className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]">salir</button>
        </form>
      </nav>

      {/* === MOBILE === */}
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
          <Link href="/blog" className={linkCls}>De manera urgente</Link>
          <Link href="/biblioteca/consultorio" className="text-accent hover:text-ink transition-colors">Pregúntale al viento</Link>
          <Link href="/biblioteca?mode=semantic#search" className="text-accent hover:text-ink transition-colors">Como lo diría Robe</Link>
          <Link href="/biblioteca/donar" className={linkCls}>Apoyar el proyecto</Link>
          {isAdmin && <Link href="/biblioteca/admin/sources" className={linkCls}>Admin</Link>}
          <form action="/logout" method="post"><button type="submit" className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]">salir</button></form>
        </nav>
      </details>
    </header>
  );
}
