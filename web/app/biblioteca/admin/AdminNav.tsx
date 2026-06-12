"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS: { href: string; label: string }[] = [
  { href: "/biblioteca/admin/sources", label: "fuentes" },
  { href: "/biblioteca/admin/seo", label: "SEO content" },
  { href: "/biblioteca/admin/blog", label: "Blog" },
  { href: "/biblioteca/admin/instagram", label: "Instagram" },
  { href: "/biblioteca/admin/users", label: "usuarios" },
  { href: "/biblioteca/admin/subscribers", label: "suscriptores" },
];

export default function AdminNav() {
  const pathname = usePathname() || "";
  return (
    <nav className="font-mono text-[10px] tracking-[2px] uppercase flex flex-wrap gap-4">
      {ITEMS.map((it) => {
        const active = pathname.startsWith(it.href);
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
