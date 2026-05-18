import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import SeoListWithBulk from "./SeoListWithBulk";

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
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <h1 className="font-serif text-4xl md:text-5xl text-ink leading-[1.1] tracking-[-0.5px]">
            Contenido SEO
          </h1>
          <Link
            href="/biblioteca/admin/seo/templates"
            data-cursor="hover"
            className="font-mono text-[11px] tracking-[2px] uppercase text-ink-dim hover:text-accent border border-divider hover:border-accent px-3 py-1.5 transition-colors"
          >
            plantillas SEO →
          </Link>
        </div>
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

      <SeoListWithBulk items={items} />
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
