import Link from "next/link";
import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import SeoListWithBulk from "./SeoListWithBulk";
import { AdminPage, Metric, MetricGrid, filterClass } from "@/components/admin/ui";

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
  { value: "all", label: "Todas" },
  { value: "unreviewed", label: "Sin revisar" },
  { value: "reviewed", label: "Revisadas, sin publicar" },
  { value: "published", label: "Publicadas" },
];

const TYPES = [
  { value: "all", label: "Todos" },
  { value: "artist", label: "Artistas" },
  { value: "album", label: "Discos" },
  { value: "song", label: "Canciones" },
  { value: "person", label: "Personas" },
  { value: "band", label: "Grupos" },
  { value: "theme", label: "Temas" },
  { value: "place", label: "Lugares" },
  { value: "concept", label: "Conceptos" },
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
    unreviewed: items.filter((i) => !i.reviewed_at && !i.published).length,
    pending: items.filter((i) => i.reviewed_at && !i.published).length,
    published: items.filter((i) => i.published).length,
  };

  return (
    <AdminPage
      title="Fichas SEO"
      intro="Los textos de cada ficha (canciones, discos, personas…). Revisa, edita y publica: solo lo publicado se ve en la web."
    >
      <MetricGrid>
        <Metric label="En este filtro" value={counts.total} />
        <Metric label="Sin revisar" value={counts.unreviewed} tone={counts.unreviewed > 0 ? "warn" : "neutral"} />
        <Metric label="Revisadas, sin publicar" value={counts.pending} tone={counts.pending > 0 ? "warn" : "neutral"} />
        <Metric label="Publicadas" value={counts.published} />
      </MetricGrid>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2" aria-label="Filtrar por estado">
          <span className="text-sm text-ink-faint w-14">Estado</span>
          {STATUSES.map((s) => (
            <Link
              key={s.value}
              href={`/biblioteca/admin/seo?status=${s.value}&entity_type=${entity_type}`}
              aria-current={status === s.value ? "page" : undefined}
              className={filterClass(status === s.value)}
            >
              {s.label}
            </Link>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-label="Filtrar por tipo">
          <span className="text-sm text-ink-faint w-14">Tipo</span>
          {TYPES.map((t) => (
            <Link
              key={t.value}
              href={`/biblioteca/admin/seo?status=${status}&entity_type=${t.value}`}
              aria-current={entity_type === t.value ? "page" : undefined}
              className={filterClass(entity_type === t.value)}
            >
              {t.label}
            </Link>
          ))}
        </div>
      </div>

      <SeoListWithBulk items={items} />
    </AdminPage>
  );
}
