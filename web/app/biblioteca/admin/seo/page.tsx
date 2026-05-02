import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";

type SeoListItem = {
  id: number;
  entity_type: string;
  slug: string;
  entity_label: string;
  chars: number;
  generated_at: string;
  generated_by: string;
  reviewed_at: string | null;
  published: boolean;
};

export const metadata = {
  title: "Admin · SEO content · Entre Interiores",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

const STATUSES = [
  { value: "all", label: "todos" },
  { value: "unreviewed", label: "sin revisar" },
  { value: "reviewed", label: "revisados sin publicar" },
  { value: "published", label: "publicados" },
];

const TYPES = [
  { value: "all", label: "todos" },
  { value: "artist", label: "artista" },
  { value: "album", label: "disco" },
  { value: "song", label: "canción" },
];

export default async function AdminSeoPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; entity_type?: string }>;
}) {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/seo");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  const { status = "all", entity_type = "all" } = await searchParams;
  const items = await apiFetch<SeoListItem[]>(
    `/admin/seo?status=${status}&entity_type=${entity_type}`,
  );

  const counts = {
    total: items.length,
    unreviewed: items.filter((i) => !i.reviewed_at).length,
    pending: items.filter((i) => i.reviewed_at && !i.published).length,
    published: items.filter((i) => i.published).length,
  };

  return (
    <main className="px-5 md:px-14 py-10 md:py-14 max-w-[1100px] mx-auto">
      <Link
        href="/biblioteca/admin/sources"
        data-cursor="hover"
        className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-ink"
      >
        ← admin
      </Link>

      <header className="mt-6 mb-10">
        <p className="font-mono text-[10px] tracking-[3px] uppercase text-accent mb-2">
          panel admin
        </p>
        <h1 className="font-serif text-4xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
          Contenido SEO
        </h1>
        <p className="font-serif italic text-ink-dim text-lg mt-3 max-w-2xl">
          Revisa, edita y publica los artículos generados por LLM. Solo los
          publicados son visibles en la capa pública SEO.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8 text-center">
          <Stat label="total" value={counts.total} />
          <Stat label="sin revisar" value={counts.unreviewed} />
          <Stat label="revisados pendientes" value={counts.pending} />
          <Stat label="publicados" value={counts.published} />
        </div>
      </header>

      <div className="flex flex-wrap gap-x-4 gap-y-2 mb-2 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint">
        <span>filtro estado:</span>
        {STATUSES.map((s) => (
          <Link
            key={s.value}
            href={`/biblioteca/admin/seo?status=${s.value}&entity_type=${entity_type}`}
            data-cursor="hover"
            className={`hover:text-accent ${
              status === s.value ? "text-accent" : ""
            }`}
          >
            {s.label}
          </Link>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-2 mb-8 font-mono text-[10px] tracking-[2px] uppercase text-ink-faint border-b border-divider pb-4">
        <span>filtro tipo:</span>
        {TYPES.map((t) => (
          <Link
            key={t.value}
            href={`/biblioteca/admin/seo?status=${status}&entity_type=${t.value}`}
            data-cursor="hover"
            className={`hover:text-accent ${
              entity_type === t.value ? "text-accent" : ""
            }`}
          >
            {t.label}
          </Link>
        ))}
      </div>

      {items.length === 0 ? (
        <p className="font-serif italic text-ink-faint">
          No hay artículos con esos filtros.
        </p>
      ) : (
        <ul className="divide-y divide-divider border-t border-divider">
          {items.map((it) => (
            <li key={it.id}>
              <Link
                href={`/biblioteca/admin/seo/${it.id}`}
                data-cursor="hover"
                className="grid grid-cols-[auto_1fr_auto_auto] gap-4 items-baseline py-3.5 hover:bg-paper/40 transition-colors px-2 -mx-2"
              >
                <span
                  className="font-mono text-[10px] tracking-[1.5px] uppercase text-ink-faint w-14"
                  title={it.entity_type}
                >
                  {it.entity_type}
                </span>
                <span className="font-serif text-ink truncate">
                  {it.entity_label}
                </span>
                <span className="font-mono text-[10px] tracking-[1px] text-ink-faint">
                  {it.chars} ch
                </span>
                <span className="font-mono text-[10px] tracking-[1.5px] uppercase">
                  {it.published ? (
                    <span className="text-accent">publicado</span>
                  ) : it.reviewed_at ? (
                    <span className="text-accent/60">revisado</span>
                  ) : (
                    <span className="text-ink-faint">sin revisar</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-divider py-4">
      <p className="font-mono text-[9px] tracking-[2px] uppercase text-ink-faint">
        {label}
      </p>
      <p className="font-serif text-3xl text-ink mt-1">{value}</p>
    </div>
  );
}
