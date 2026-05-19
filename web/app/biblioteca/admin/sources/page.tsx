import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import SourceForm from "./SourceForm";

type SourceListItem = {
  id: number;
  kind: string;
  url: string;
  title: string | null;
  author: string | null;
  fetched_at: string;
  referenced_song_ids: number[] | null;
  n_referenced: number;
};

export const dynamic = "force-dynamic";

export default async function AdminSourcesPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/sources");
  }
  if (!me!.is_admin) {
    redirect("/biblioteca");
  }

  let sources: SourceListItem[] = [];
  try {
    sources = await apiFetch<SourceListItem[]>("/admin/sources?limit=20");
  } catch {
    sources = [];
  }

  return (
    <main className="px-5 md:px-14 py-10 md:py-16 max-w-5xl mx-auto">
      <header className="mb-12">
        <div className="flex items-center justify-between mb-2">
          <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent">
            panel admin
          </p>
          <nav className="font-mono text-[10px] tracking-[2px] uppercase flex gap-4">
            <span className="text-accent">fuentes</span>
            <Link href="/biblioteca/admin/seo" data-cursor="hover" className="text-ink-dim hover:text-accent">
              SEO content
            </Link>
            <Link href="/biblioteca/admin/posts" data-cursor="hover" className="text-ink-dim hover:text-accent">
              Diario
            </Link>
            <Link href="/biblioteca/admin/users" data-cursor="hover" className="text-ink-dim hover:text-accent">
              usuarios
            </Link>
            <Link href="/biblioteca/admin/subscribers" data-cursor="hover" className="text-ink-dim hover:text-accent">
              suscriptores
            </Link>
          </nav>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl text-ink mb-3">
          Alta de fuentes fan
        </h1>
        <p className="font-serif italic text-ink-dim text-lg max-w-2xl">
          Sube nuevos análisis de la comunidad: texto pegado, blog/foro para scrapear, o transcript de un vídeo de YouTube. Tras subir, dispara re-destilación + vectorización para las canciones afectadas.
        </p>
      </header>

      <SourceForm />

      <section className="mt-20">
        <h2 className="font-mono text-[10px] tracking-[3px] uppercase text-ink-dim mb-5">
          últimas fuentes ({sources.length})
        </h2>
        {sources.length === 0 ? (
          <p className="font-serif italic text-ink-faint">No hay fuentes registradas todavía.</p>
        ) : (
          <ul className="divide-y divide-divider border-t border-divider">
            {sources.map((s) => (
              <li key={s.id} className="py-4 flex items-start justify-between gap-6">
                <div className="min-w-0 flex-1">
                  <p className="font-serif text-lg text-ink truncate">
                    {s.title || s.url}
                  </p>
                  <p className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint mt-1">
                    {s.kind} · {s.author || "sin autor"} · {new Date(s.fetched_at).toLocaleDateString("es-ES")}
                  </p>
                  <Link
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[10px] text-accent hover:underline truncate block"
                  >
                    {s.url}
                  </Link>
                </div>
                <div className="text-right shrink-0">
                  <span className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-dim">
                    {s.n_referenced} canción{s.n_referenced === 1 ? "" : "es"}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
