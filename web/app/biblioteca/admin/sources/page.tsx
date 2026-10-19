import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import SourceForm from "./SourceForm";
import { AdminPage, Card, EmptyState, Section, StatusBadge } from "@/components/admin/ui";

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
    <AdminPage
      title="Fuentes"
      intro="Añade análisis de la comunidad (un texto, un blog, un vídeo) al corpus. Es material de fondo: orienta lo que se escribe, pero nunca se cita ni se nombra a su autor."
    >
      <Card>
        <SourceForm />
      </Card>

      <Section title="Últimas fuentes añadidas" count={sources.length}>
        {sources.length === 0 ? (
          <EmptyState>No hay fuentes registradas todavía.</EmptyState>
        ) : (
          <ul className="divide-y divide-divider rounded-md border border-divider">
            {sources.map((s) => (
              <li key={s.id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-serif text-lg text-ink truncate">{s.title || s.url}</p>
                  <p className="text-sm text-ink-faint">
                    {s.kind} · {s.author || "sin autor"} ·{" "}
                    {new Date(s.fetched_at).toLocaleDateString("es-ES")}
                  </p>
                  <Link
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-xs text-accent hover:underline truncate block"
                  >
                    {s.url}
                  </Link>
                </div>
                <StatusBadge tone={s.n_referenced > 0 ? "info" : "neutral"}>
                  {s.n_referenced} canción{s.n_referenced === 1 ? "" : "es"}
                </StatusBadge>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </AdminPage>
  );
}
