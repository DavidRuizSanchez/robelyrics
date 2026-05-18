import Link from "next/link";
import { safeJsonLd } from "@/lib/safe-json-ld";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://entreinteriores.com";

export type Crumb = {
  label: string;
  href: string;
  meta?: string;
};

export default function Breadcrumbs({
  items,
  className = "",
}: {
  items: Crumb[];
  className?: string;
}) {
  if (items.length === 0) return null;

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.label,
      item: c.href.startsWith("http") ? c.href : `${SITE_URL}${c.href}`,
    })),
  };

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
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jsonLd) }}
      />
    </>
  );
}
