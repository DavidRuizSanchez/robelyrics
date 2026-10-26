"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Item = { href: string; label: string };

// Agrupado por para qué sirve cada pantalla, no por orden de creación.
const GRUPOS: { titulo: string; items: Item[] }[] = [
  {
    titulo: "Contenido",
    items: [
      { href: "/biblioteca/admin/blog", label: "Blog" },
      { href: "/biblioteca/admin/seo", label: "Fichas SEO" },
      { href: "/biblioteca/admin/seo/oportunidades", label: "Oportunidades SEO" },
    ],
  },
  { titulo: "Redes", items: [{ href: "/biblioteca/admin/instagram", label: "Instagram" }] },
  {
    titulo: "Calidad",
    items: [
      { href: "/biblioteca/admin/erratas", label: "Erratas" },
      { href: "/biblioteca/admin/corpus", label: "Corpus" },
      { href: "/biblioteca/admin/cambios", label: "Cambios" },
      { href: "/biblioteca/admin/sources", label: "Fuentes" },
    ],
  },
  {
    titulo: "Audiencia",
    items: [
      { href: "/biblioteca/admin/uso", label: "Uso" },
      { href: "/biblioteca/admin/users", label: "Usuarios" },
      { href: "/biblioteca/admin/subscribers", label: "Suscriptores" },
    ],
  },
];

const INICIO = "/biblioteca/admin";

export default function AdminNav() {
  const pathname = usePathname() || "";
  // Con dos rutas anidadas («/seo» y «/seo/oportunidades») el prefijo solo no
  // vale: encendía las dos a la vez. Manda la coincidencia más específica.
  const activo =
    pathname === INICIO
      ? INICIO
      : GRUPOS.flatMap((g) => g.items.map((it) => it.href))
          .filter((href) => pathname === href || pathname.startsWith(href + "/"))
          .sort((a, b) => b.length - a.length)[0];
  const cls = (href: string) =>
    `rounded px-2 py-1 transition-colors ${
      href === activo
        ? "bg-paper-hi text-ink font-medium"
        : "text-ink-dim hover:text-ink hover:bg-paper"
    }`;
  return (
    <nav
      aria-label="Secciones del panel"
      className="flex flex-wrap items-center gap-x-6 gap-y-3 pb-4 border-b border-divider text-sm"
    >
      <Link href={INICIO} aria-current={activo === INICIO ? "page" : undefined} className={cls(INICIO)}>
        Inicio
      </Link>
      {GRUPOS.map((g) => (
        <div key={g.titulo} className="flex items-center gap-1">
          <span className="text-[11px] uppercase tracking-wider text-ink-faint mr-1">
            {g.titulo}
          </span>
          {g.items.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              aria-current={it.href === activo ? "page" : undefined}
              className={cls(it.href)}
            >
              {it.label}
            </Link>
          ))}
        </div>
      ))}
    </nav>
  );
}
