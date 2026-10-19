import { redirect } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { AuthMe } from "@/lib/types";
import { AdminPage, Callout, EmptyState, Metric, MetricGrid, Section } from "@/components/admin/ui";

export const dynamic = "force-dynamic";

type FeatureCount = { feature: string; total: number };
type UsageSummary = {
  days: number;
  by_feature: FeatureCount[];
  consultorio_total: number;
  consultorio_sin_respuesta: number;
};
type TopQuery = { query: string; veces: number };

const FEATURE_LABEL: Record<string, string> = {
  consultorio: "Pregúntale al viento",
  search: "Buscador semántico",
  complete: "Completar",
  mood: "Listas por mood",
};

export default async function AdminUsoPage() {
  let me: AuthMe;
  try {
    me = await apiFetch<AuthMe>("/auth/me");
  } catch {
    redirect("/login?from=/biblioteca/admin/uso");
  }
  if (!me!.is_admin) redirect("/biblioteca");

  let summary: UsageSummary | null = null;
  let topConsultorio: TopQuery[] = [];
  let topSearch: TopQuery[] = [];
  try {
    [summary, topConsultorio, topSearch] = await Promise.all([
      apiFetch<UsageSummary>("/admin/usage/summary?days=30"),
      apiFetch<TopQuery[]>("/admin/usage/top?feature=consultorio&days=30&limit=15"),
      apiFetch<TopQuery[]>("/admin/usage/top?feature=search&days=30&limit=15"),
    ]);
  } catch {
    // vacío
  }

  const noResRate =
    summary && summary.consultorio_total > 0
      ? Math.round((summary.consultorio_sin_respuesta / summary.consultorio_total) * 100)
      : 0;

  return (
    <AdminPage
      title="Uso"
      intro="Cuánto se usa cada herramienta en los últimos 30 días y qué pregunta la gente. El total de visitas está en GA4."
    >
      <Section title="Usos por herramienta · últimos 30 días">
        {!summary || summary.by_feature.length === 0 ? (
          <EmptyState>Aún no hay datos de uso registrados.</EmptyState>
        ) : (
          <MetricGrid>
            {summary.by_feature.map((f) => (
              <Metric
                key={f.feature}
                label={FEATURE_LABEL[f.feature] || f.feature}
                value={f.total.toLocaleString("es-ES")}
              />
            ))}
          </MetricGrid>
        )}
        {summary && summary.consultorio_total > 0 && (
          <Callout
            tone={noResRate > 0 ? "warn" : "ok"}
            className="mt-4"
            title={`«Pregúntale al viento» no supo responder ${summary.consultorio_sin_respuesta} de ${summary.consultorio_total} preguntas (${noResRate} %)`}
          >
            Son huecos de contenido: temas por los que pregunta la gente y de los que el corpus no
            tiene material.
          </Callout>
        )}
      </Section>

      <div className="grid md:grid-cols-2 gap-10">
        <Section title="Lo más preguntado al viento">
          <TopList items={topConsultorio} />
        </Section>
        <Section title="Lo más buscado">
          <TopList items={topSearch} />
        </Section>
      </div>
    </AdminPage>
  );
}

function TopList({ items }: { items: TopQuery[] }) {
  if (items.length === 0) {
    return <EmptyState>Nada aún.</EmptyState>;
  }
  return (
    <ol className="divide-y divide-divider rounded-md border border-divider">
      {items.map((q, i) => (
        <li key={i} className="flex items-baseline justify-between gap-3 px-3 py-2">
          <span className="font-mono text-xs text-ink-faint w-5 shrink-0">{i + 1}</span>
          <span className="flex-1 font-serif text-[15px] text-ink truncate">{q.query}</span>
          <span className="text-sm text-ink-dim shrink-0">
            {q.veces.toLocaleString("es-ES")} {q.veces === 1 ? "vez" : "veces"}
          </span>
        </li>
      ))}
    </ol>
  );
}
