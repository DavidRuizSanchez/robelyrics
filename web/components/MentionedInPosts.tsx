import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { PublicPostListItem } from "@/lib/types";

// Bloque "Mencionado en" — enlaces internos contextuales hacia los posts
// del blog que mencionan esta entidad (persona, artista, álbum, canción).
// Sirve a SEO (linkado interno relevante) y a navegación lateral.

export default async function MentionedInPosts({
  slug,
  limit = 6,
  heading = "Mencionado en",
}: {
  slug: string;
  limit?: number;
  heading?: string;
}) {
  let items: PublicPostListItem[] = [];
  try {
    items = await apiFetch<PublicPostListItem[]>(
      `/public/posts/mentioning?slug=${encodeURIComponent(slug)}&limit=${limit}`,
      { authenticated: false },
    );
  } catch {
    return null;
  }
  if (items.length === 0) return null;

  return (
    <section className="mt-16 border-t border-divider pt-10">
      <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-6">
        {heading}
      </h2>
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-8">
        {items.map((p) => (
          <li key={p.slug}>
            <Link
              href={`/blog/${p.slug}`}
              data-cursor="hover"
              className="group block"
            >
              <p className="font-mono text-[10px] tracking-[2px] uppercase text-ink-faint mb-2">
                {kindLabel(p.kind)}
              </p>
              <h3 className="font-serif text-lg md:text-xl text-ink leading-snug group-hover:text-accent transition-colors">
                {p.title}
              </h3>
              {p.excerpt && (
                <p className="mt-2 font-serif italic text-ink-dim text-sm leading-relaxed line-clamp-3">
                  {p.excerpt}
                </p>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    editorial: "Editorial",
    news: "Noticia",
    anniversary: "Efeméride",
    "album-anniversary": "Aniversario",
    spotlight: "Análisis",
    evergreen: "Editorial",
  };
  return map[kind] || kind;
}
