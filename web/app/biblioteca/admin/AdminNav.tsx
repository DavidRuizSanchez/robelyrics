"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS: { href: string; label: string }[] = [
  { href: "/biblioteca/admin/sources", label: "fuentes" },
  { href: "/biblioteca/admin/seo", label: "SEO content" },
  { href: "/biblioteca/admin/seo/oportunidades", label: "oportunidades" },
  { href: "/biblioteca/admin/blog", label: "Blog" },
  { href: "/biblioteca/admin/erratas", label: "erratas" },
  { href: "/biblioteca/admin/uso", label: "uso" },
  { href: "/biblioteca/admin/instagram", label: "Instagram" },
  { href: "/biblioteca/admin/users", label: "usuarios" },
  { href: "/biblioteca/admin/subscribers", label: "suscriptores" },
];

export default function AdminNav() {
  const pathname = usePathname() || "";
  // Con dos rutas anidadas («/seo» y «/seo/oportunidades») el prefijo solo no
  // vale: encendía las dos a la vez. Manda la coincidencia más específica.
  const activo = ITEMS.map((it) => it.href)
    .filter((href) => pathname === href || pathname.startsWith(href + "/"))
    .sort((a, b) => b.length - a.length)[0];
  return (
    <nav className="font-mono text-[10px] tracking-[2px] uppercase flex flex-wrap gap-4">
      {ITEMS.map((it) => {
        const active = it.href === activo;
        return (
          <Link
            key={it.href}
            href={it.href}
            data-cursor="hover"
            className={active ? "text-accent" : "text-ink-dim hover:text-accent"}
          >
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}
