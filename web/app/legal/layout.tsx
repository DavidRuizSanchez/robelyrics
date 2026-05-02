import Link from "next/link";

const PAGES = [
  { href: "/legal/aviso", label: "Aviso legal" },
  { href: "/legal/privacidad", label: "Privacidad" },
  { href: "/legal/cookies", label: "Cookies" },
  { href: "/legal/terminos", label: "Términos de uso" },
  { href: "/legal/takedown", label: "Takedown" },
  { href: "/legal/atribuciones", label: "Atribuciones" },
];

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-3xl mx-auto">
      <Link
        href="/"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← inicio
      </Link>
      <nav className="mt-8 mb-12 flex flex-wrap gap-x-4 gap-y-2 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint border-b border-divider pb-4">
        {PAGES.map((p) => (
          <Link
            key={p.href}
            href={p.href}
            data-cursor="hover"
            className="hover:text-accent transition-colors"
          >
            {p.label}
          </Link>
        ))}
      </nav>
      <article className="prose prose-invert max-w-none font-serif text-ink-dim leading-[1.7] [&_h1]:font-serif [&_h1]:text-3xl [&_h1]:text-ink [&_h1]:mb-6 [&_h2]:font-serif [&_h2]:text-xl [&_h2]:text-ink [&_h2]:mt-8 [&_h2]:mb-3 [&_p]:my-4 [&_a]:text-accent [&_a]:underline">
        {children}
      </article>
    </main>
  );
}
