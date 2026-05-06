"use client";

import Link from "next/link";
import { useState } from "react";
import LogoBomba from "@/components/LogoBomba";

export default function Header({ isAdmin = false }: { isAdmin?: boolean }) {
  const [open, setOpen] = useState(false);
  const items = [
    { href: "/biblioteca", label: "Inicio" },
    { href: "/biblioteca/discografia", label: "Discografía" },
    ...(isAdmin ? [{ href: "/biblioteca/admin/sources", label: "Admin" }] : []),
  ];
  return (
    <header className="sticky top-0 z-40 flex items-center justify-between px-5 md:px-14 py-4 md:py-6 border-b border-divider bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/70">
      <Link
        href="/biblioteca"
        data-cursor="hover"
        className="flex items-center gap-3"
        aria-label="Entre Interiores · inicio"
      >
        <LogoBomba size={44} />
        <span className="font-serif text-lg md:text-xl text-ink leading-none tracking-tight">
          Entre Interiores
        </span>
      </Link>

      <nav className="hidden md:flex items-center gap-8 font-mono text-[11px] tracking-[2.5px] uppercase">
        {items.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            data-cursor="hover"
            className="text-ink-dim hover:text-ink transition-colors"
          >
            {it.label}
          </Link>
        ))}
        <form action="/logout" method="post" className="inline">
          <button
            type="submit"
            data-cursor="hover"
            className="text-ink-faint hover:text-ink transition-colors font-mono uppercase tracking-[2.5px]"
          >
            salir
          </button>
        </form>
      </nav>

      <button
        type="button"
        onClick={() => setOpen(!open)}
        data-cursor="hover"
        className="md:hidden text-ink font-mono text-sm tracking-[2px]"
        aria-label="Menu"
      >
        {open ? "✕" : "☰"}
      </button>

      {open && (
        <div className="md:hidden absolute top-full left-0 right-0 bg-bg border-b border-divider px-5 pb-5 pt-2">
          {items.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              onClick={() => setOpen(false)}
              className="block py-3 font-mono text-xs tracking-[2px] uppercase text-ink border-b border-divider"
            >
              {it.label}
            </Link>
          ))}
          <form action="/logout" method="post">
            <button
              type="submit"
              className="block py-3 font-mono text-xs tracking-[2px] uppercase text-ink-faint w-full text-left"
            >
              salir
            </button>
          </form>
        </div>
      )}
    </header>
  );
}
