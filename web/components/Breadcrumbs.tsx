import Link from "next/link";

export type Crumb = {
  label: string;
  href: string;
  meta?: string;
};

// El JSON-LD BreadcrumbList ya NO se emite aquí: va dentro del @graph de cada
// página (web/lib/schema-graph.ts → breadcrumbListNode). Este componente es
// solo el <nav> visual. Así hay un único <script> JSON-LD por página.
export default function Breadcrumbs({
  items,
  className = "",
}: {
  items: Crumb[];
  className?: string;
}) {
  if (items.length === 0) return null;

  return (
    <>
      <nav
        aria-label="breadcrumb"
        className={`font-mono text-[11px] tracking-[2px] uppercase text-ink-dim ${className}`}
      >
        <ol className="flex flex-wrap items-center gap-2">
          {items.map((c, i) => {
            const isLast = i === items.length - 1;
            return (
              <li key={c.href} className="flex items-center gap-2">
                {isLast ? (
                  <span aria-current="page" className="text-ink">
                    {c.label}
                    {c.meta && (
                      <span className="text-ink-faint ml-2">{c.meta}</span>
                    )}
                  </span>
                ) : (
                  <>
                    <Link
                      href={c.href}
                      data-cursor="hover"
                      className="hover:text-ink"
                    >
                      {c.label}
                    </Link>
                    {c.meta && (
                      <span className="text-ink-faint">{c.meta}</span>
                    )}
                    <span className="opacity-50">·</span>
                  </>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    </>
  );
}
